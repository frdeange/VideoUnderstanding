# VideoUnderstanding: Azure OpenAI Video Description & TTS Demo

This project is a complete demo that allows you to analyze short videos, generate automatic scene descriptions using Azure OpenAI vision models, and synthesize an audio narration (TTS) that is overlaid on the original video. The result is an accessible video, ideal for visually impaired users or to enhance the accessibility of audiovisual content.

## What does this project do?
- Lets you upload a video from a modern, accessible web interface.
- Extracts key frames from the video, skipping duplicates.
- Uses Azure OpenAI (GPT-4o Vision) to describe each visual segment briefly and accurately.
- Converts each description to audio using Azure OpenAI TTS (Text-to-Speech).
- Generates a new video with the narration overlaid and displays both the descriptions and the final video in the web UI.

## Project structure
- `main.py`: FastAPI backend that handles upload, analysis, description generation, and audio synthesis.
- `frontend/`: Modern web interface (HTML, CSS, JS) for user interaction.
- `.env.fake`: Template for environment variables needed to connect to Azure OpenAI.
- `.devcontainer/`: Configuration for a ready-to-use development environment in VS Code.

## Requirements

### Recommended: Use the Dev Container
The project includes a `.devcontainer` with everything you need:
- Python 3, pip
- Node.js, npm
- ffmpeg
- Azure CLI
- Python and Azure extensions for VS Code

**Just open the project in VS Code and select "Reopen in Container".**

### Manual option (without devcontainer)
If you prefer to run it in your own environment, make sure you have:
- Python 3.10+
- pip
- ffmpeg (must be in your PATH)
- Node.js and npm (only if you want to modify the frontend)
- Azure CLI (optional, for connection tests)
- Recommended: Python virtual environment

Install Python dependencies:
```bash
pip install -r requirements.txt
```

## Environment variable setup
1. **Copy `.env.fake` to `.env`:**
   ```bash
   cp .env.fake .env
   ```
2. **Edit `.env` and fill in your real Azure OpenAI keys and endpoints:**
   - `AOAI_VIDEO_ENDPOINT`, `AOAI_VIDEO_API_KEY`, `AOAI_VIDEO_DEPLOYMENT`, `AOAI_VIDEO_API_VERSION`
   - `AOAI_TTS_ENDPOINT`, `AOAI_TTS_API_KEY`, `AOAI_TTS_DEPLOYMENT`, `AOAI_TTS_API_VERSION`, `AOAI_TTS_VOICE`
   - Adjust `APP_FRAME_RATE` if you want to change the frame analysis frequency.

## How to run the project

1. **Start the backend:**
   ```bash
   python3 main.py
   ```
   (Or use `uvicorn main:app --reload` for hot-reload)

2. **Open the web interface:**
   - Go to `http://localhost:8000` (or the port shown by FastAPI) in your browser

3. **Upload a video and wait for analysis.**
   - You will see the generated descriptions and can play the narrated video.

## Additional notes
- The system is optimized for short videos (≤40 MB).
- Processing time depends on video length and Azure API speed.
- If you have issues with ffmpeg, make sure it is installed and accessible from your command line.

## Credits
Project created by Kiko de Ángel [LinkedIn](https://www.linkedin.com/in/fdangel/)

---
Enjoy creating accessible videos with the power of Azure OpenAI!
