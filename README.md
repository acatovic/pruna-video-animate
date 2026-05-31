# Pruna Video Animate

Animate a local reference image using the motion and audio from a local reference video through Pruna's `p-video-animate` model.

**NOTE:**

* For best results it helps if the reference image is compositionally as close as possible to the starting video sequence; for example if the subject is sitting down in a chair with a close-up in the video, the reference image should also be in a seated close-up position. *Tip:* use an image generation model to create your reference image in the same composition as the video reference.
* The quality of the generated video deteriorates dramatically as the video length increases - for best results cut up the video into smaller pieces of 15-20 seconds in length and after generation coalesce them together using e.g. `ffmpeg`.
* If the video has dramatic compositional changes, you will need to separate those and use reference images that align with those compisitions, e.g. if the starting sequence is seated-closeup, and the next sequence is walking side-view, they will need a separate reference image for best results.

**DEMO:**


https://github.com/user-attachments/assets/1fddcba8-e93c-481a-9c25-c1af51fc4a2d



## Setup

```bash
uv sync --extra dev
cp .env.example .env
```

Edit `.env` and set:

```bash
PRUNA_API_KEY=your_pruna_api_key
```

The API key is read from `PRUNA_API_KEY` and is never printed.

## Usage


```bash
uv run pruna-animate reference-image.png reference-video.mp4 --output animated.mp4
```

The tool uploads the video first, uploads the image second, creates an async `p-video-animate` prediction, polls until completion, and downloads the generated MP4.

## Tests

Automated tests mock Pruna HTTP calls and do not contact the real API.

```bash
uv run pytest
```
