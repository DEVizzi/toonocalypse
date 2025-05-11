from google import genai
import replicate
from google.genai import types
import os
import subprocess
import random
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import SystemMessage, HumanMessage
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from datetime import datetime
from google.cloud import aiplatform
from google.cloud import aiplatform_v1beta1
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Value
import cv2
import numpy as np

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# YouTube OAuth scope and token endpoint
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"

# Load API key from .env
load_dotenv()

IG_ACCESS_TOKEN=os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID=os.getenv("IG_USER_ID")
BASE_URL = "https://graph.facebook.com/v17.0"
GENAI_KEY = os.getenv("GOOGLE_API_KEY")
POEM_HISTORY_FILE = "poem_history.txt"


# Setup Gemini LLM
llm = ChatGoogleGenerativeAI(
    model="models/gemini-1.5-flash",
    temperature=0.85,
    api_key=GENAI_KEY
)

# Define poetic styles and prompts (max 4–5 lines output expected)
poem_styles = {
    "Nature": [
        "Write a short nature poem (max 4 lines) that celebrates a quiet morning.",
        "Compose a 3-line verse about the wind whispering through autumn leaves.",
        "Capture the feeling of sunrise over a still lake in no more than 4 lines.",
        "Write 4 poetic lines about a hidden waterfall in the forest.",
        "In 3 lines, express the silence of snowfall in the mountains."
    ],
    "Romantic": [
        "Write a romantic poem in 3 or 4 lines, inspired by a fleeting glance.",
        "Create a 4-line love poem comparing affection to moonlight on water.",
        "Compose a 3-line love note that feels timeless.",
        "Write a 4-line verse about a memory of someone you still dream about.",
        "In 3 lines, describe how love feels when words fall short."
    ],
    "Epic": [
        "Write a 4-line heroic poem about a lone warrior facing the storm.",
        "Summarize an epic quest through desert and flame in 3 poetic lines.",
        "In 4 lines, compose a poem about the fall of a mighty kingdom.",
        "Create a short verse (max 4 lines) about a sword passed down generations.",
        "Write 3 lines capturing the final stand of a forgotten hero."
    ],
    "Mystical": [
        "Write a 4-line mystical poem about moonlight and forgotten spells.",
        "In 3 lines, describe a forest where time stands still.",
        "Compose a short mystical verse about stars guiding lost souls.",
        "Write a 4-line poem about a mirror that shows other worlds.",
        "Create a 3-line enchantment about a night where dreams come alive."
    ],
    "Melancholic": [
        "Write a 3-line poem about the quiet ache of memory.",
        "In 4 lines, describe the beauty in solitude.",
        "Compose a short melancholic verse about rain on a windowpane.",
        "Write a poem (max 4 lines) about a letter never sent.",
        "In 3 lines, evoke the feeling of a goodbye without closure."
    ],
    "Whimsical": [
        "Write a 3-line poem about a cat who dreams of the stars.",
        "In 4 lines, create a verse where teacups talk and clocks dance.",
        "Compose a short whimsical poem about a child befriending a cloud.",
        "Write a 3-line rhyme about socks that vanish to another realm.",
        "In 4 lines, describe a street where gravity forgot to work."
    ],
    "Inspirational": [
        "Write a 3-line poem that sparks hope in the darkest hour.",
        "In 4 lines, compose a verse about rising after failure.",
        "Create a short inspirational poem about chasing dreams.",
        "Write a 3-line reminder that light always returns.",
        "In 4 lines, capture the courage to begin again."
    ],
    "Haunting": [
        "Write a 4-line poem that feels like a forgotten ghost story.",
        "In 3 lines, describe a shadow that follows but never speaks.",
        "Compose a haunting verse about an abandoned house in 4 lines.",
        "Write a short poem about whispers in the dark.",
        "In 3 lines, capture the fear of waking in a dream."
    ],
    "Philosophical": [
        "Write a 3-line poem that questions time itself.",
        "In 4 lines, explore the illusion of control.",
        "Compose a short verse about the paradox of existence.",
        "Write a 3-line poem on the nature of truth.",
        "In 4 lines, muse on the soul’s journey through life."
    ],
    "Seasonal": [
        "Write a 3-line spring poem about renewal and bloom.",
        "In 4 lines, capture the colors and chaos of autumn.",
        "Create a short poem about winter stillness.",
        "Write a 4-line verse about summer sunsets and long shadows.",
        "In 3 lines, depict the first snow as a fresh canvas."
    ],
    "Dreamlike": [
        "Write a 4-line dream-poem where nothing makes sense yet feels real.",
        "In 3 lines, describe floating through clouds of memory.",
        "Compose a dreamlike poem about falling into starlight.",
        "Write a 4-line verse set in a place that only exists at 3AM.",
        "In 3 lines, make the reader feel like they’re waking up from magic."
    ],
    "Minimalist": [
        "Write a poem in just 3 lines using only 3–5 words per line.",
        "In 4 lines, express something vast with the fewest words.",
        "Compose a minimalist verse about silence.",
        "Write a short poem where each word must count.",
        "In 3 lines, reduce emotion to its essence."
    ]
}

def write_poem_bottom_center(image_path: str, poem: str, output_path: str = None) -> str:
    """
    Write the poem in white at the bottom center of the image, center-aligned with an elegant font,
    over a semi-transparent black background.
    """
    # Open the original image and ensure it's in RGBA mode
    base_image = Image.open(image_path).convert("RGBA")
    width, height = base_image.size

    # Create an overlay image for the semi-transparent rectangle and text
    overlay = Image.new('RGBA', base_image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    # Load poetic font
    try:
        font_path = "font/Esteban-Regular.ttf"  # Update to your actual font path
        font_size = width // 22
        font = ImageFont.truetype(font_path, font_size)
    except Exception as e:
        print(f"⚠️ Font load failed: {e}. Using default font.")
        font = ImageFont.load_default()
        font_size = font.getsize("A")[1]

    lines = poem.strip().split("\n")
    spacing = int(font_size * 0.6)

    # Calculate total height of the poem block
    line_heights = [draw.textbbox((0, 0), line, font=font)[3] for line in lines]
    total_text_height = sum(line_heights) + (len(lines) - 1) * spacing

    y_start = height - total_text_height - 100  # 100px padding from bottom

    # Determine the width of the widest line
    max_line_width = max([draw.textlength(line, font=font) for line in lines])

    # Define rectangle coordinates with padding
    padding_x = 40
    padding_y = 20
    rect_x0 = (width - max_line_width) / 2 - padding_x
    rect_y0 = y_start - padding_y
    rect_x1 = (width + max_line_width) / 2 + padding_x
    rect_y1 = y_start + total_text_height + padding_y

    # Draw semi-transparent black rectangle
    draw.rectangle([(rect_x0, rect_y0), (rect_x1, rect_y1)], fill=(0, 0, 0, 128))

    # Draw each line of the poem
    y = y_start
    for line in lines:
        line_width = draw.textlength(line, font=font)
        x = (width - line_width) / 2
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += font_size + spacing

    # Composite the overlay with the base image
    combined = Image.alpha_composite(base_image, overlay)

    # Save the final image
    if not output_path:
        output_path = os.path.splitext(image_path)[0] + "_poem.png"
    combined.convert("RGB").save(output_path)
    print(f"📝 Poem written to bottom-center with semi-transparent background: {output_path}")
    return output_path

def select_poem_style(poem_styles: dict) -> str:
    """
    Select a random poem style from the provided dictionary.
    """
    return random.choice(list(poem_styles.keys()))

def generate_poem(style: str, poem_styles: dict) -> str:
    """
    Generate a new short poem using the specified style and prompt.
    """
    seen = set()
    fallback_poem = "Night whispers low\nThrough silent trees aglow\nA dream begins to grow."

    if os.path.exists(POEM_HISTORY_FILE):
        with open(POEM_HISTORY_FILE, "r", encoding="utf-8") as f:
            seen = set(line.strip() for line in f if line.strip())

    prompts = poem_styles.get(style, [])
    if not prompts:
        print(f"No prompts found for style: {style}")
        return fallback_poem

    for _ in range(3):
        prompt = random.choice(prompts)
        msgs = [
            SystemMessage(content="You are a poetic assistant. Respond with a 3 to 5 line poem. No title, no explanations."),
            HumanMessage(content=prompt)
        ]
        try:
            response = llm.invoke(msgs).content.strip()
        except Exception:
            continue

        if not response or response in seen or response.count("\n") > 4:
            continue

        seen.add(response)
        with open(POEM_HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(response + "\n")
        print(f"\n[Style: {style}]\n")
        return response

    print(f"\n[Style: {style}] (fallback)\n")
    return fallback_poem


'''
# IMAGE GENERATOR Hugging Face Black Forest Labs FREE
def generate_image_from_prompt(prompt: str) -> Image.Image:
    """
    Generate an image using Hugging Face's Inference API with the FLUX.1-dev model.
    """
    api_token = os.getenv("HUGGINGFACE_API_TOKEN")
    if not api_token:
        raise RuntimeError("HUGGINGFACE_API_TOKEN not set in environment.")

    endpoint = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-dev"
    
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    payload = {"inputs": prompt}
    print(f"🖼️ Generating image for prompt:\n{prompt}")
    response = requests.post(endpoint, headers=headers, json=payload)

    if response.status_code == 503:
        raise RuntimeError("Model is loading. Please wait and try again.")
    elif response.status_code != 200:
        raise RuntimeError(f"Image generation failed: {response.status_code} — {response.text}")

    return Image.open(BytesIO(response.content))

'''
# IMAGE GENERATOR REPLICATE Black Forest Labs $0.003/image
def generate_image_from_prompt(prompt: str) -> str:
    """
    Generate a 3:4 aspect ratio image using Replicate's flux-schnell model
    and save it with a timestamped filename.
    Returns the full path to the saved image.
    """
    api_token = os.getenv("REPLICATE_API_TOKEN")
    if not api_token:
        raise RuntimeError("REPLICATE_API_TOKEN not set in environment")

    client = replicate.Client(api_token=api_token)

    input = {
        "prompt": prompt,
        "width": 768,      # Width for 3:4 aspect ratio
        "height": 1024     # Height for 3:4 aspect ratio
    }

    output = client.run("black-forest-labs/flux-schnell", input=input)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_paths = []

    for index, item in enumerate(output):
        filename = f"poem_image_{timestamp}_{index}.webp"
        with open(filename, "wb") as f:
            f.write(item.read())
        image_paths.append(filename)

    print(f"✅ Image(s) saved to: {', '.join(image_paths)}")
    return image_paths[0]  # return the first image path



'''
# IMAGE GENERATOR Google Gemini FREE
def generate_image_from_prompt(prompt: str) -> str:
    """
    Generate an ultra-HD, clean image with no embedded text using Gemini API.
    Returns the file path of the saved image.
    """
    try:
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

        enhanced_prompt = (
            f"{prompt.strip()}\n\n"
            "Generate an ultra high-definition (UHD) image, minimum 4K visual quality. "
            "The image should contain no overlaid text, labels, words, or symbols. "
            "Do not add any captions or annotations. Focus on cinematic detail, texture, color, and depth. "
            "Ensure the composition is vertical (3:4 or 1:1 aspect ratio)."
        )

        response = client.models.generate_content(
            model="gemini-2.0-flash-exp-image-generation",
            #model="gemini-2.0-flash-preview-image-generation",
            contents=enhanced_prompt,
            config=types.GenerateContentConfig(
                response_modalities=['TEXT', 'IMAGE']
            )
        )

        # Only extract the image part
        for part in response.candidates[0].content.parts:
            if hasattr(part, "inline_data") and part.inline_data is not None:
                image = Image.open(BytesIO(part.inline_data.data))

                # Optional: upscale if image is small (simulate UHD)
                if image.width < 2000:
                    # Use thumbnail to maintain aspect ratio
                    max_size = (2000, 2000)
                    image.thumbnail(max_size, Image.LANCZOS)

                filename = "gemini_ultrahd_image.png"
                image.save(filename)
                print(f"✅ UHD Image saved as {filename}")
                return filename

        raise RuntimeError("❌ No image found in Gemini response.")

    except Exception as e:
        print(f"⚠️ Gemini image generation failed: {e}")
        raise
'''


'''
#IMAGE GENERATOR ChainGPT
def generate_image_from_prompt(prompt: str, poem: str = "") -> str:
    """
    Generate an image from ChainGPT's image API, overlay text on it, and save the final result.
    Returns the path to the final image.
    """
    # 1. Call ChainGPT API
    url = "https://api.chaingpt.org/nft/generate-image"
    headers = {
        "Authorization": f"Bearer {os.getenv('CHAINGPT_API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {
        "prompt": prompt,
        "model": "velogen",
        "steps": 3,
        "height": 1024,
        "width": 1024,
        "enhance": "1x"
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        byte_list = response.json().get("image", {}).get("data")
        if not byte_list:
            raise ValueError("No image data returned.")
    except Exception as e:
        raise RuntimeError(f"⚠️ ChainGPT image generation failed: {e}")

    # 2. Convert byte array to image
    try:
        image_bytes = bytes(byte_list)
        image = Image.open(BytesIO(image_bytes)).convert("RGBA")
    except Exception as e:
        raise RuntimeError(f"⚠️ Failed to decode image: {e}")

    # 3. Overlay poem on the image
    draw = ImageDraw.Draw(image)
    width, height = image.size

    # Load font (fallback if Esteban not available)
    try:
        font_path = "font/Esteban-Regular.ttf"  # Replace with your actual font path
        font_size = width // 22
        font = ImageFont.truetype(font_path, font_size)
    except:
        font = ImageFont.load_default()

    lines = poem.strip().split("\n")
    spacing = font_size * 0.6
    total_height = sum([draw.textbbox((0, 0), line, font=font)[3] for line in lines]) + (len(lines) - 1) * spacing
    y_start = height - total_height - 80
    x_center = width // 2

    for line in lines:
        line_width = draw.textlength(line, font=font)
        x = x_center - line_width / 2
        draw.text((x, y_start), line, font=font, fill="white")
        y_start += font_size + spacing

    # 4. Save final image
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_path = f"chaingpt_poem_image_{timestamp}.png"
    image.save(final_path)
    print(f"✅ Image with poem saved to {final_path}")
    return final_path

'''
'''
#VertexAI
def generate_image_from_prompt(prompt: str) -> str:
    """
    Generate an image using Vertex AI Imagen model via PredictionServiceClient.
    """
    client = aiplatform_v1beta1.PredictionServiceClient()

    project = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GCP_REGION", "us-central1")
    endpoint = f"projects/{project}/locations/{location}/publishers/google/models/imagen"

    instance = {
        "prompt": prompt,
        "image": {
            "size": {
                "width": 300,
                "height": 300
            }
        }
    }

    instances = [json_format.ParseDict(instance, Value())]
    parameters = json_format.ParseDict({}, Value())

    try:
        response = client.predict(endpoint=endpoint, instances=instances, parameters=parameters)
        img_data = base64.b64decode(response.predictions[0]["bytesBase64Encoded"])
        image = Image.open(BytesIO(img_data))

        filename = f"vertex_imagen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        image.save(filename)
        print(f"✅ Image saved as {filename}")
        return filename

    except Exception as e:
        print(f"⚠️ Image generation failed: {e}")
        raise
'''
#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
'''
#Poetic scene 1
def reform_poem_to_scenic_prompt(poem: str) -> str:
    """
    Use LangChain to convert a poem into an epic, cinematic, vertical, emotionally resonant painting-style prompt.
    """
    poem_text = " ".join(line.strip() for line in poem.split("\n") if line.strip())

    system_msg = SystemMessage(
        content=(
            "You are a poetic visual storyteller. "
            "Convert short poems into scenic, cinematic prompts for AI-generated art. "
            "Your output should describe an emotionally powerful and relatable visual scene, "
            "rendered as an epic digital painting. Include artistic details like atmosphere, colors, light, emotion, and scene composition. "
            "Always make it vertical (portrait), 3:4 aspect ratio, and suitable for Instagram. "
            "Focus on visual storytelling that evokes emotion — awe, peace, wonder, or hope."
        )
    )

    user_msg = HumanMessage(
        content=f"Transform this poem into a vivid, vertical scenic prompt for an epic painting:\n\"{poem_text}\""
    )

    try:
        refined_prompt = llm.invoke([system_msg, user_msg]).content.strip()
        # Style tail to ensure quality and format
        styled_prompt = (
            refined_prompt +
            ", epic digital painting, hyper-detailed, cinematic lighting, soft gradients, emotionally resonant, 3:4 vertical composition"
        )
        return styled_prompt
    except Exception as e:
        print(f"Prompt refinement failed: {e}")
        return f"A vertical scenic digital painting illustrating: {poem_text}, cinematic light, emotional realism, 3:4"

'''

#poetic scene 2
def reform_poem_to_scenic_prompt(poem: str) -> str:
    """
    Convert a short poem into a rich, cinematic, multi-layered scenic prompt
    suitable for breathtaking AI-generated imagery.
    """
    poem_text = " ".join(line.strip() for line in poem.split("\n") if line.strip())

    system_msg = SystemMessage(
        content=(
            "You are a masterful visual prompt writer. "
            "Transform poetic text into prompts for breathtaking scenic digital paintings. "
            "The image should be vivid, multi-element, and highly detailed — combining elements such as mountains, forests, rivers, skies, light, human silhouettes, animals, flowers, temples, or nature trails. "
            "Use layered composition with foreground, midground, and background depth. "
            "Ensure strong cinematic lighting, emotional tone (awe, wonder, peace), and visual storytelling. "
            "The final image must be in a vertical format (3:4 or 1:1 aspect ratio) and should not contain any text or captions. "
        )
    )

    user_msg = HumanMessage(
        content=f"Convert this poem into a breathtaking scenic prompt with high visual diversity and emotional power:\n\"{poem_text}\""
    )

    try:
        refined_prompt = llm.invoke([system_msg, user_msg]).content.strip()

        # Add consistent style and compositional direction
        styled_prompt = (
            refined_prompt +
            ", ultra-detailed textures, soft ambient light, vertical 3:4 or 1:1 aspect ratio"
        )
        return styled_prompt
    except Exception as e:
        print(f"Prompt refinement failed: {e}")
        return f"An epic scenic vertical digital painting inspired by: {poem_text}, with rich natural diversity, cinematic glow, emotional realism, 3:4 ratio"


'''
#poetic scene 3
def reform_poem_to_scenic_prompt(poem: str) -> str:
    """
    Convert a poem into a rich, multi-layered, vertical scenic prompt for breathtaking AI-generated artwork.
    """
    poem_text = " ".join(line.strip() for line in poem.split("\n") if line.strip())

    system_msg = SystemMessage(
        content=(
            "You are a poetic visual storyteller who transforms short poems into breathtaking visual prompts. "
            "Create an expansive, richly detailed scenic description that looks like a magical dream world. "
            "Include diverse elements such as majestic mountains, flowing rivers, vibrant flowers, mystical forests, ancient ruins, animals, birds in flight, clouds, and glowing skies. "
            "The scene should feel emotionally moving — evoking awe, wonder, serenity, or adventure. "
            "Describe atmospheric lighting (e.g., golden hour, moonlight, misty morning), vivid colors, dynamic compositions, depth layers (foreground, midground, background), and fine artistic textures. "
            "Ensure it is vertical (portrait), with a 3:4 aspect ratio, ideal for epic digital paintings or Instagram stories."
        )
    )

    user_msg = HumanMessage(
        content=f"Transform this short poem into a rich and scenic visual prompt:\n\"{poem_text}\""
    )

    try:
        refined_prompt = llm.invoke([system_msg, user_msg]).content.strip()
        styled_prompt = (
            refined_prompt +
            ", fantasy realism, ultra detailed, layered environment, sweeping landscape, cinematic lighting, 3:4 vertical composition, digital painting style"
        )
        return styled_prompt
    except Exception as e:
        print(f"Prompt refinement failed: {e}")
        return (
            f"An expansive scenic digital painting based on: {poem_text}, with rivers, mountains, forests, sky, and animals, "
            "golden hour lighting, layered composition, 3:4 portrait"
        )
'''



def combine_image_with_music_ffmpeg(image_path: str, poem_style: str, duration: int = 30) -> str:
    """
    Combine a poetic image with music to create a 30-second vertical video using FFmpeg.
    Selects a random .mp3 file from the /music/{poem_style}/ directory.
    """
    
    if poem_style in ["Dreamlike", "Minimalist"]:
        poem_style = "Nature"

    music_dir = os.path.join("music", poem_style)
    if not os.path.isdir(music_dir):
        raise FileNotFoundError(f"⚠️ Music directory not found: {music_dir}")

    # List all .mp3 files in the music directory
    music_files = [f for f in os.listdir(music_dir) if f.lower().endswith('.mp3')]
    if not music_files:
        raise FileNotFoundError(f"⚠️ No .mp3 files found in {music_dir}")

    # Select a random music file
    music_path = os.path.join(music_dir, random.choice(music_files))

    output_path = os.path.splitext(image_path)[0] + '_video.mp4'

    command = [
        'ffmpeg',
        '-y',
        '-loop', '1',
        '-i', image_path,
        '-i', music_path,
        '-t', str(duration),
        '-vf', 'scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2',
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',
        '-shortest',
        output_path
    ]

    subprocess.run(command, check=True)
    print(f"🎬 Video created: {output_path}")
    return output_path



def generate_caption_from_poem(poem: str) -> str:
    return (
        poem.strip() +'''
        
🌅 Escape into emotion.
Follow @poeminpixels for breathtaking cinematic poetry that blends visuals with human soul.
🎥✨ Every reel is a visual poem — where pixels meet passion, and art becomes an experience.

🔮 #PoetryInMotion #EpicVisuals #AIArtistry #CinematicPoetry #ReelArt #DigitalDreams #EmotionOnScreen #FantasyFrames #PoeticVibes #ReelsOfWonder'''
    )


#*****************************INSTAGRAM***BEGIN***********************************
def init_reel_upload(caption: str, cover_url: str = None) -> (str, str):
    endpoint = f"{BASE_URL}/{IG_USER_ID}/media"
    params = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN
    }
    if cover_url:
        params["cover_url"] = cover_url
    resp = requests.post(endpoint, data=params).json()
    if "id" not in resp or "uri" not in resp:
        raise RuntimeError(f"Error initializing reel upload: {resp}")
    return resp["id"], resp["uri"]

def upload_reel_video(upload_url: str, video_path: str) -> None:
    file_size = os.path.getsize(video_path)
    headers = {
        "Authorization": f"OAuth {IG_ACCESS_TOKEN}",
        "offset": "0",
        "file_size": str(file_size)
    }
    with open(video_path, "rb") as f:
        resp = requests.post(upload_url, headers=headers, data=f)
    data = resp.json() if resp.headers.get('Content-Type', '').startswith('application/json') else {}
    if not resp.ok or (data.get("success") is False):
        raise RuntimeError(f"Error uploading reel video: {data or resp.text}")

def publish_media_container(container_id: str) -> dict:
    endpoint = f"{BASE_URL}/{IG_USER_ID}/media_publish"
    params = {
        "creation_id": container_id,
        "access_token": IG_ACCESS_TOKEN
    }
    resp = requests.post(endpoint, data=params).json()
    if "id" not in resp:
        raise RuntimeError(f"Error publishing media: {resp}")
    return resp

def post_reel(video_path: str, caption: str, cover_url: str = None) -> str:
    container_id, upload_url = init_reel_upload(caption, cover_url)
    upload_reel_video(upload_url, video_path)
    res = publish_media_container(container_id)
    return f"✅ Reel posted successfully (media ID: {res['id']})"
#*****************************INSTAGRAM***END*************************************

def preprocess_image(image_path: str, style: str) -> str:
    """
    Improve low-quality images: denoise, upscale, apply fantasy-like beautification.
    """
    image = Image.open(image_path).convert("RGB")
    width, height = image.size

    # Step 1: Crop to 3:4
    target_ratio = 3 / 4
    if width / height > target_ratio:
        new_width = int(height * target_ratio)
        left = (width - new_width) // 2
        image = image.crop((left, 0, left + new_width, height))
    else:
        new_height = int(width / target_ratio)
        top = (height - new_height) // 2
        image = image.crop((0, top, width, top + new_height))

    # Step 2: Denoise and smooth
    image = image.filter(ImageFilter.MedianFilter(size=3))  # Reduce noise

    # Step 3: Resize to HD
    image = image.resize((1080, 1440), Image.LANCZOS)

    # Step 4: Gentle enhancement (no harsh sharpening)
    image = ImageEnhance.Color(image).enhance(1.4)
    image = ImageEnhance.Contrast(image).enhance(1)
    image = ImageEnhance.Brightness(image).enhance(0.9)
    image = ImageEnhance.Sharpness(image).enhance(1.1)  # Very mild

    # Step 5: Add soft cinematic glow
    glow = image.filter(ImageFilter.GaussianBlur(radius=1.5))
    image = Image.blend(image, glow, alpha=0.12)

    processed_path = os.path.splitext(image_path)[0] + "_enhanced.jpg"
    image.save(processed_path, quality=95)
    print(f"🛠️ Low-quality image improved and saved: {processed_path}")
    return processed_path


def make_instagram_reel_frame(image_path: str) -> str:
    """
    Creates a 1080x1920 vertical reel frame from any image.
    Centers the image and fills background with a blurred version of itself.
    """
    output_size = (1080, 1920)
    image = Image.open(image_path).convert("RGB")

    # Step 1: Resize background to fill full 1080x1920
    bg = image.copy()
    bg = bg.resize(output_size, Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=18))  # Soft background

    # Step 2: Resize foreground to fit safely within frame (e.g. max height 1600)
    fg_max_height = 1600
    fg_max_width = 1080

    img_ratio = image.width / image.height
    if image.height > fg_max_height or image.width > fg_max_width:
        if img_ratio > (fg_max_width / fg_max_height):
            new_width = fg_max_width
            new_height = int(fg_max_width / img_ratio)
        else:
            new_height = fg_max_height
            new_width = int(fg_max_height * img_ratio)
        image = image.resize((new_width, new_height), Image.LANCZOS)

    # Step 3: Composite foreground over blurred background
    final_image = bg.copy()
    paste_x = (output_size[0] - image.width) // 2
    paste_y = (output_size[1] - image.height) // 2
    final_image.paste(image, (paste_x, paste_y))

    # Step 4: Save
    output_path = os.path.splitext(image_path)[0] + "_reel_1080x1920.jpg"
    final_image.save(output_path, quality=95)
    print(f"🎬 Instagram Reel-ready image saved: {output_path}")
    return output_path    

#********************************Youtube Start************************************************************
def authenticate_youtube():
    """
    Authenticate to YouTube using refresh token flow. 
    Requires env vars: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
    """
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri=TOKEN_URI,
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)

def upload_video_to_youtube(video_path: str, title: str, description: str, tags: list = None) -> str:
    """
    Upload a video to YouTube and return the video ID.
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    
    title = title.strip().replace("\n", " ")[:100] or "Cinematic Poem"

    youtube = authenticate_youtube()
    
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": "22"  # People & Blogs
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"📤 Upload progress: {int(status.progress() * 100)}%")

    print(f"✅ Uploaded to YouTube: https://youtu.be/{response['id']}")
    return response["id"]

#********************************Youtube End**************************************************************


if __name__ == "__main__":
    
    style = select_poem_style(poem_styles)

    poem = generate_poem(style, poem_styles)

    print("\nGenerated Poem:\n", poem)
    
    tags_list = [style.lower(), "cinematic", "poetry", "ai", "visuals"]
    
    try:
        scenic_prompt = reform_poem_to_scenic_prompt(poem)
        print(f"\n🎨 Scenic Prompt:\n{scenic_prompt}")
        
        image_path = generate_image_from_prompt(scenic_prompt)
        
        #processed_path = preprocess_image(image_path, style)
        processed_path=make_instagram_reel_frame(image_path)
        
        final_image_path = write_poem_bottom_center(processed_path, poem)
        print(f"✅ Image saved to {final_image_path}")
        
        if style in ["Dreamlike", "Minimalist"]:
            style = "Nature"
        video_path = combine_image_with_music_ffmpeg(final_image_path,style)

        # 2. Generate caption
        caption = generate_caption_from_poem(poem)
        print(f"✅ Caption: {caption}")
        
        # 3. Publish to Instagram
        post_reel(video_path, caption)
        
        # 4. Publish to Youtube
        yt_id = upload_video_to_youtube(video_path, title=poem, description=caption, tags=tags_list)
        print(f"✅ YouTube Shorts uploaded: https://youtu.be/{yt_id}")
        
    except Exception as e:
        print(f"⚠️ Failed : {e}")


