from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

import aiofiles
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from openai import AzureOpenAI

# ───────── Load .env ───────── #
load_dotenv()

# ───────── Vision (video → Text) settings ───────── #
VIDEO_ENDPOINT: str = os.getenv("AOAI_VIDEO_ENDPOINT", "")
VIDEO_KEY: str = os.getenv("AOAI_VIDEO_API_KEY", "")
VIDEO_API_VERSION: str = os.getenv("AOAI_VIDEO_API_VERSION", "2024-12-01-preview")
VIDEO_DEPLOYMENT: str | None = os.getenv("AOAI_VIDEO_DEPLOYMENT")

# ───────── TTS (Text → audio) settings ───────── #
TTS_ENDPOINT: str | None = os.getenv("AOAI_TTS_ENDPOINT")
TTS_KEY: str | None = os.getenv("AOAI_TTS_API_KEY")
TTS_API_VERSION: str = os.getenv("AOAI_TTS_API_VERSION", "2025-03-01-preview")
TTS_DEPLOYMENT: Optional[str] = os.getenv("AOAI_TTS_DEPLOYMENT")
TTS_VOICE: str = os.getenv("AOAI_TTS_VOICE", "alloy")

# ───────── App tuning ───────── #
APP_FRAME_RATE: float = float(os.getenv("APP_FRAME_RATE", 1))

# ───────── Azure OpenAI clients ───────── #
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

# ───────── FastAPI app ───────── #
app = FastAPI(title="Video → Vision → TTS demo (dual resources)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ───────── Helpers ───────── #

def _extract_frames(video: Path, out: Path, fps: float) -> List[Path]:
    """
    Extracts frames at fixed fps, then removes near-duplicate frames.
    """
    out.mkdir(parents=True, exist_ok=True)
    # sample at specified fps and drop duplicates
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


def _vision_payload(frames: List[Path]):
    return [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{_b64(p)}",
                "detail": "high",
            },
        }
        for p in frames
    ]

# ───────── Routes ───────── #

@app.post("/analyze")
async def analyze(file: UploadFile):
    if not VIDEO_DEPLOYMENT:
        return JSONResponse({"error": "AOAI_VIDEO_DEPLOYMENT not set"}, 500)

    # Save upload
    with tempfile.TemporaryDirectory() as td:
        video_path = Path(td) / file.filename
        async with aiofiles.open(video_path, "wb") as out:
            while chunk := await file.read(1 << 20):
                await out.write(chunk)

        # extract frames filtered by mpdecimate to skip duplicates
        frames_dir = Path(td) / "frames"
        frames = _extract_frames(video_path, frames_dir, APP_FRAME_RATE)

        if not frames:
            return JSONResponse({"error": "No se pudieron extraer fotogramas"}, 400)
        descriptions: List[str] = []
        # describe each key segment
        for idx, frame in enumerate(frames, start=1):
            timestamp = (idx - 1) / APP_FRAME_RATE
            # vision description for this frame
            messages = [
                {"role": "system", "content": (
                    "Eres un asistente que describe imágenes para personas con discapacidad visual. "
                    "Proporciona una descripción muy breve en una sola frase, evitando prefijos como 'en la imagen' o 'en la pantalla'. "
                    "Enfócate en el sujeto y la acción principal. No solicites más contexto ni incluyas marcas de tiempo."
                )},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Describe en una frase lo que sucede en el segundo {timestamp:.2f} del vídeo."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64(frame)}", "detail": "high"}},
                    ],
                }
            ]
            resp = video_client.chat.completions.create(model=VIDEO_DEPLOYMENT, messages=messages, max_tokens=64)
            desc = resp.choices[0].message.content.strip()
            descriptions.append(desc)
        # generate per-frame TTS chunks to preserve all details
        audio_chunks: List[Path] = []
        for idx, desc in enumerate(descriptions, start=1):
            tts_resp = tts_client.audio.speech.create(
                model=TTS_DEPLOYMENT, voice=TTS_VOICE,
                input=desc, response_format="wav"
            )
            chunk_path = Path(td) / f"chunk_{idx:04d}.wav"
            chunk_path.write_bytes(tts_resp.content)
            audio_chunks.append(chunk_path)
        # concatenate chunks and overlay on video
        video_b64 = None
        if audio_chunks:
            concat_file = Path(td) / "concat.txt"
            with open(concat_file, 'w') as cf:
                for p in audio_chunks:
                    cf.write(f"file '{p.name}'\n")
            full_audio = Path(td) / "full_audio.wav"
            subprocess.run([
                "ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_file),
                "-c", "copy", str(full_audio), "-loglevel", "error", "-y"
            ], check=True)
            output_video = Path(td) / f"{video_path.stem}_desc.mp4"
            # adjust audio speed to fit video duration
            # get durations
            video_dur = float(subprocess.check_output([
                'ffprobe','-v','error','-select_streams','v:0',
                '-show_entries','stream=duration','-of','default=noprint_wrappers=1:nokey=1', str(video_path)
            ]).decode().strip())
            audio_dur = float(subprocess.check_output([
                'ffprobe','-v','error','-show_entries','format=duration',
                '-of','default=noprint_wrappers=1:nokey=1', str(full_audio)
            ]).decode().strip())
            # calculate speed factor: speed up if narration longer than video
            ratio = (audio_dur / video_dur) if video_dur > 0 else 1.0
            adjusted_audio = full_audio
            # only speed up when audio exceeds video length
            if ratio > 1.01:
                adjusted_audio = Path(td) / "adjusted_audio.wav"
                # chain atempo filters within [0.5-100]
                temp_ratio = ratio
                filters: list[str] = []
                # break down for ratio >100
                while temp_ratio > 100.0:
                    filters.append('atempo=100')
                    temp_ratio /= 100.0
                # remaining factor (should be between 1.0 and 100.0)
                filters.append(f'atempo={temp_ratio:.6f}')
                filter_str = ','.join(filters)
                subprocess.run([
                    'ffmpeg', '-i', str(full_audio), '-filter:a', filter_str,
                    str(adjusted_audio), '-loglevel', 'error', '-y'
                ], check=True)
            # merge video and adjusted audio
            subprocess.run([
                "ffmpeg", "-i", str(video_path), "-i", str(adjusted_audio),
                "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0",
                "-shortest", str(output_video), "-loglevel", "error", "-y"
            ], check=True)
            video_b64 = base64.b64encode(output_video.read_bytes()).decode()
        # response
        resp = {"descriptions": descriptions}
        if video_b64:
            resp["video"] = video_b64
        return JSONResponse(resp)


# Swagger helper
@app.get("/docs", include_in_schema=False)
async def docs_redirect():
    return RedirectResponse("/redoc")


# Global error handler
@app.exception_handler(Exception)
async def global_handler(_: Request, exc: Exception):
    return JSONResponse({"error": str(exc)}, 500)

# Montar frontend estático al final para no interceptar POST /analyze
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
