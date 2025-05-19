# mainalternative.py
"""
Alternative version of the main app, with Azure Blob Storage integration (identity), multilingual support, and prepared for later queries about videos and captures.
"""

import os
from pathlib import Path
from typing import List, Optional
import base64
import tempfile
import subprocess
import uuid

import aiofiles
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, Request, Form, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from openai import AzureOpenAI
from pydantic import BaseModel

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

# -------- Load .env -------- #
load_dotenv()

# -------- Azure Blob Storage settings -------- #
BLOB_ACCOUNT_NAME = os.getenv("AZURE_BLOB_ACCOUNT_NAME")
BLOB_CONTAINER_PROJECT = os.getenv("AZURE_BLOB_CONTAINER_PROJECT", "videoproject")
BLOB_ACCOUNT_URL = f"https://{BLOB_ACCOUNT_NAME}.blob.core.windows.net"

# -------- Vision (video → Text) settings -------- #
VIDEO_ENDPOINT: str = os.getenv("AOAI_VIDEO_ENDPOINT", "")
VIDEO_KEY: str = os.getenv("AOAI_VIDEO_API_KEY", "")
VIDEO_API_VERSION: str = os.getenv("AOAI_VIDEO_API_VERSION", "2024-12-01-preview")
VIDEO_DEPLOYMENT: str | None = os.getenv("AOAI_VIDEO_DEPLOYMENT")

# -------- TTS (Text → audio) settings -------- #
TTS_ENDPOINT: str | None = os.getenv("AOAI_TTS_ENDPOINT")
TTS_KEY: str | None = os.getenv("AOAI_TTS_API_KEY")
TTS_API_VERSION: str = os.getenv("AOAI_TTS_API_VERSION", "2025-03-01-preview")
TTS_DEPLOYMENT: Optional[str] = os.getenv("AOAI_TTS_DEPLOYMENT")
# Supported voices for OpenAI TTS (front-end options: 2 male, 2 female, labels in Spanish for UI)
TTS_VOICES = {
    "ballad": "Masculina 1 (Ballad)",
    "ash": "Masculina 2 (Ash)",
    "alloy": "Femenina 1 (Alloy)",
    "sage": "Femenina 2 (Sage)"
}
TTS_DEFAULT_VOICE = "ballad"

# -------- App tuning -------- #
APP_FRAME_RATE: float = float(os.getenv("APP_FRAME_RATE", 1))

# -------- Azure OpenAI clients -------- #
video_client = AzureOpenAI(
    api_key=VIDEO_KEY,
    azure_endpoint=VIDEO_ENDPOINT,
    api_version=VIDEO_API_VERSION,
)

tts_client: Optional[AzureOpenAI] = None
if TTS_ENDPOINT and TTS_KEY and TTS_DEPLOYMENT:
    tts_client = AzureOpenAI(
        api_key=TTS_KEY,
        azure_endpoint=TTS_ENDPOINT,
        api_version=TTS_API_VERSION,
    )

# -------- Blob path helpers -------- #
def get_blob_path(video_id: str, kind: str, filename: str) -> str:
    """
    Returns the blob path for a given kind: 'userUpload', 'frames', 'audioChunks', 'videoResult'.
    """
    if kind == "userUpload":
        return f"{video_id}/userUpload/{filename}"
    elif kind == "frames":
        return f"{video_id}/frames/{filename}"
    elif kind == "audioChunks":
        return f"{video_id}/audioChunks/{filename}"
    elif kind == "videoResult":
        return f"{video_id}/videoResult/{filename}"
    else:
        raise ValueError("Invalid blob kind")

# -------- Azure Blob Storage client (identity) -------- #
credential = DefaultAzureCredential()
blob_service_client = BlobServiceClient(account_url=BLOB_ACCOUNT_URL, credential=credential)
project_container = blob_service_client.get_container_client(BLOB_CONTAINER_PROJECT)

# -------- FastAPI app -------- #
app = FastAPI(title="Video → Vision → TTS demo (Azure Blob, multilingual)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# -------- Helpers -------- #
def _extract_frames(video: Path, out: Path, fps: float) -> List[Path]:
    out.mkdir(parents=True, exist_ok=True)
    vf = f"fps={fps},mpdecimate"
    cmd = [
        "ffmpeg", "-i", str(video), "-vf", vf,
        "-vsync", "vfr", str(out / "%04d.jpg"),
        "-loglevel", "error", "-y",
    ]
    subprocess.run(cmd, check=True)
    return sorted(out.glob("*.jpg"))

def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()

# -------- Get prompt and voice -------- #
def _get_prompt_and_voice(lang: str, timestamp: float, voice: str = None) -> tuple[str, str, str]:
    # Initialize prompt and user_text by default
    prompt = ""
    user_text = ""
    if lang == "en":
        prompt = (
            "You are an assistant describing images for visually impaired people. "
            "Provide a very brief description in a single sentence, avoiding prefixes like 'in the image' or 'on the screen'. "
            "Focus on the main subject and action. Do not request more context or include timestamps."
        )
        user_text = f"Describe in one sentence what happens at second {timestamp:.2f} of the video."
    elif lang == "es":
        prompt = (
            "Eres un asistente que describe imágenes para personas con discapacidad visual. "
            "Proporciona una descripción muy breve en una sola frase, evitando prefijos como 'en la imagen' o 'en la pantalla'. "
            "Enfócate en el sujeto y la acción principal. No solicites más contexto ni incluyas marcas de tiempo."
        )
        user_text = f"Describe en una frase lo que sucede en el segundo {timestamp:.2f} del vídeo."
    else:
        # fallback to English if the language is not valid
        prompt = (
            "You are an assistant describing images for visually impaired people. "
            "Provide a very brief description in a single sentence, avoiding prefixes like 'in the image' or 'on the screen'. "
            "Focus on the main subject and action. Do not request more context or include timestamps."
        )
        user_text = f"Describe in one sentence what happens at second {timestamp:.2f} of the video."
    # If the voice is not valid, use the default one
    if voice not in TTS_VOICES:
        voice = TTS_DEFAULT_VOICE
    return prompt, user_text, voice

# -------- Routes -------- #
@app.post("/upload-video")
async def upload_video(file: UploadFile = File(...)):
    """
    Uploads a video and stores it in blob storage. Returns video_id and filename.
    """
    video_id = str(uuid.uuid4())
    video_blob_name = get_blob_path(video_id, "userUpload", file.filename)
    with tempfile.TemporaryDirectory() as td:
        video_path = Path(td) / file.filename
        async with aiofiles.open(video_path, "wb") as out:
            while chunk := await file.read(1 << 20):
                await out.write(chunk)
        with open(video_path, "rb") as data:
            project_container.upload_blob(name=video_blob_name, data=data, overwrite=True)
    return {"video_id": video_id, "filename": file.filename}

class ExtractFramesRequest(BaseModel):
    video_id: str
    filename: str

@app.post("/extract-frames")
async def extract_frames_api(req: ExtractFramesRequest):
    """
    Extracts frames from the uploaded video and stores them in blob storage. Returns frame paths.
    """
    video_blob_name = get_blob_path(req.video_id, "userUpload", req.filename)
    with tempfile.TemporaryDirectory() as td:
        video_path = Path(td) / req.filename
        # Download video
        with open(video_path, "wb") as out:
            blob = project_container.download_blob(video_blob_name)
            out.write(blob.readall())
        frames_dir = Path(td) / "frames"
        frames = _extract_frames(video_path, frames_dir, APP_FRAME_RATE)
        frame_blob_names = []
        for frame in frames:
            frame_blob_name = get_blob_path(req.video_id, "frames", frame.name)
            with open(frame, "rb") as data:
                project_container.upload_blob(name=frame_blob_name, data=data, overwrite=True)
            frame_blob_names.append(frame_blob_name)
    return {"video_id": req.video_id, "frames": frame_blob_names}

class AnalyzeFramesRequest(BaseModel):
    video_id: str
    frames: list[str]
    lang: str = "es"

@app.post("/analyze-frames")
async def analyze_frames_api(req: AnalyzeFramesRequest):
    """
    Analyzes frames and returns descriptions.
    """
    descriptions = []
    for idx, frame_blob_name in enumerate(req.frames, start=1):
        with tempfile.TemporaryDirectory() as td:
            frame_path = Path(td) / Path(frame_blob_name).name
            with open(frame_path, "wb") as out:
                blob = project_container.download_blob(frame_blob_name)
                out.write(blob.readall())
            timestamp = (idx - 1) / APP_FRAME_RATE
            prompt, user_text, _ = _get_prompt_and_voice(req.lang, timestamp)
            messages = [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64(frame_path)}", "detail": "high"}},
                    ],
                }
            ]
            try:
                resp = video_client.chat.completions.create(model=VIDEO_DEPLOYMENT, messages=messages, max_tokens=64)
                desc = resp.choices[0].message.content.strip()
            except Exception as e:
                desc = f"[Vision error: {e}]"
            descriptions.append(desc)
    return {"video_id": req.video_id, "descriptions": descriptions}

class GenerateTTSRequest(BaseModel):
    video_id: str
    descriptions: list[str]
    tts_voice: str = "ballad"

@app.post("/generate-tts")
async def generate_tts_api(req: GenerateTTSRequest):
    """
    Generates TTS audio for each description and stores the chunks in blob storage. Returns audio paths.
    """
    audio_blob_names = []
    with tempfile.TemporaryDirectory() as td:
        for idx, desc in enumerate(req.descriptions, start=1):
            try:
                tts_resp = tts_client.audio.speech.create(
                    model=TTS_DEPLOYMENT, voice=req.tts_voice,
                    input=desc, response_format="wav"
                )
                chunk_path = Path(td) / f"chunk_{idx:04d}.wav"
                chunk_path.write_bytes(tts_resp.content)
                # Use the new "kind" for the audio blob path
                audio_blob_name = get_blob_path(req.video_id, "audioChunks", chunk_path.name)
                with open(chunk_path, "rb") as data:
                    project_container.upload_blob(name=audio_blob_name, data=data, overwrite=True)
                audio_blob_names.append(audio_blob_name)
            except Exception as e:
                audio_blob_names.append(f"[TTS error: {e}]")
    return {"video_id": req.video_id, "audio_chunks": audio_blob_names}

class AssembleVideoRequest(BaseModel):
    video_id: str
    filename: str
    audio_chunks: list[str]

@app.post("/assemble-video")
async def assemble_video_api(req: AssembleVideoRequest):
    """
    Assembles the final video with narration and stores it in blob storage. Returns the final video path and base64.
    """
    video_blob_name = get_blob_path(req.video_id, "userUpload", req.filename)
    with tempfile.TemporaryDirectory() as td:
        video_path = Path(td) / req.filename
        with open(video_path, "wb") as out:
            blob = project_container.download_blob(video_blob_name)
            out.write(blob.readall())
        chunk_paths = []
        for audio_blob_name in req.audio_chunks:
            chunk_path = Path(td) / Path(audio_blob_name).name
            with open(chunk_path, "wb") as out:
                blob = project_container.download_blob(audio_blob_name)
                out.write(blob.readall())
            chunk_paths.append(chunk_path)
        concat_file = Path(td) / "concat.txt"
        with open(concat_file, 'w') as cf:
            for p in chunk_paths:
                cf.write(f"file '{p.name}'\n")
        full_audio = Path(td) / "full_audio.wav"
        subprocess.run([
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c", "copy", str(full_audio), "-loglevel", "error", "-y"
        ], check=True)
        output_video = Path(td) / f"{video_path.stem}_desc.mp4"
        video_dur = float(subprocess.check_output([
            'ffprobe','-v','error','-select_streams','v:0',
            '-show_entries','stream=duration','-of','default=noprint_wrappers=1:nokey=1', str(video_path)
        ]).decode().strip())
        audio_dur = float(subprocess.check_output([
            'ffprobe','-v','error','-show_entries','format=duration',
            '-of','default=noprint_wrappers=1:nokey=1', str(full_audio)
        ]).decode().strip())
        ratio = (audio_dur / video_dur) if video_dur > 0 else 1.0
        adjusted_audio = full_audio
        if ratio > 1.01:
            adjusted_audio = Path(td) / "adjusted_audio.wav"
            temp_ratio = ratio
            filters: list[str] = []
            while temp_ratio > 100.0:
                filters.append('atempo=100')
                temp_ratio /= 100.0
            filters.append(f'atempo={temp_ratio:.6f}')
            filter_str = ','.join(filters)
            subprocess.run([
                'ffmpeg', '-i', str(full_audio), '-filter:a', filter_str,
                str(adjusted_audio), '-loglevel', 'error', '-y'
            ], check=True)
        subprocess.run([
            "ffmpeg", "-i", str(video_path), "-i", str(adjusted_audio),
            "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0",
            "-shortest", str(output_video), "-loglevel", "error", "-y"
        ], check=True)
        video_b64 = base64.b64encode(output_video.read_bytes()).decode()
        video_result_blob = get_blob_path(req.video_id, "videoResult", output_video.name)
        with open(output_video, "rb") as data:
            project_container.upload_blob(name=video_result_blob, data=data, overwrite=True)
    return {"video_id": req.video_id, "video_result_blob": video_result_blob, "video_b64": video_b64}

class AskVideoRequest(BaseModel):
    video_id: str
    question: str
    lang: str = "es" # Optional, to adapt the system prompt if needed

@app.post("/ask-video")
async def ask_video_api(req: AskVideoRequest):
    """
    Allows the user to ask questions about a video, using its frames as context.
    """
    frame_blob_names = []
    blob_prefix = f"{req.video_id}/frames/"
    blobs = project_container.list_blobs(name_starts_with=blob_prefix)
    for blob in blobs:
        # Only process files (not directories, if any)
        if blob.name.endswith(".jpg") or blob.name.endswith(".png"): # Assuming frames are jpg or png
            frame_blob_names.append(blob.name)

    if not frame_blob_names:
        return JSONResponse({"answer": "No frames found for this video or the ID is incorrect."}, status_code=404)

    image_urls = []
    with tempfile.TemporaryDirectory() as td:
        for frame_blob_name in frame_blob_names:
            try:
                frame_path = Path(td) / Path(frame_blob_name).name
                with open(frame_path, "wb") as out_file:
                    blob_data = project_container.download_blob(frame_blob_name)
                    out_file.write(blob_data.readall())
                image_urls.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{_b64(frame_path)}"}
                })
            except Exception as e:
                # Could skip this frame or handle the error differently
                print(f"Error downloading or processing frame {frame_blob_name}: {e}")
                continue # Skip to next frame
    
    if not image_urls:
        return JSONResponse({"answer": "Could not process frames for the question."}, status_code=500)

    # Set the system prompt language
    system_prompt_text = ""
    if req.lang == "es":
        system_prompt_text = (
            "Eres un asistente de IA. Responde la pregunta del usuario basándote únicamente en el contenido de los fotogramas del vídeo proporcionados. "
            "Si los fotogramas no contienen suficiente información para responder, indica que no puedes responder con la información visual disponible."
        )
    else: # Default or 'en'
        system_prompt_text = (
            "You are an AI assistant. Answer the user's question based solely on the content of the provided video frames. "
            "If the frames do not provide enough information to answer, state that you cannot answer with the available visual information."
        )

    user_content = [{"type": "text", "text": req.question}]
    user_content.extend(image_urls) # Add all images after the question text

    messages = [
        {"role": "system", "content": system_prompt_text},
        {"role": "user", "content": user_content}
    ]

    try:
        resp = video_client.chat.completions.create(
            model=VIDEO_DEPLOYMENT, 
            messages=messages, 
            max_tokens=150 # Adjust as needed
        )
        answer = resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return JSONResponse({"answer": f"Error contacting the AI service: {e}"}, status_code=500)
    
    return {"answer": answer}

# Swagger helper
@app.get("/docs-alt", include_in_schema=False)
async def docs_redirect_alt():
    return RedirectResponse("/redoc")

# Global error handler
@app.exception_handler(Exception)
async def global_handler(_: Request, exc: Exception):
    return JSONResponse({"error": str(exc)}, 500)

# Mount static frontend at the end to not intercept POST /analyze-alt
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
