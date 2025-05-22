from google import genai
from google.cloud import texttospeech
import replicate
from google.genai import types
import os
import shutil
import subprocess
import random
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import SystemMessage, HumanMessage
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import tweepy
import time
import re
import json
import cloudinary
import cloudinary.uploader
from collections import OrderedDict
import sys


# YouTube OAuth scope and token endpoint
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"


# Load API key from .env
load_dotenv()

with open("heroes.json", "r") as file:
    heroes = json.load(file)

with open("action_story.json", "r") as file:
    action_story = json.load(file)

IG_ACCESS_TOKEN=os.getenv("IG_ACCESS_TOKEN")

IG_USER_ID=os.getenv("IG_USER_ID")
BASE_URL = "https://graph.facebook.com/v17.0"
GENAI_KEY = os.getenv("GOOGLE_API_KEY")

# TTS Function
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "myvoiceoverbot-a0da14b71e20.json"

# Setup Gemini LLM
llm = ChatGoogleGenerativeAI(
    model="models/gemini-1.5-flash",
    temperature=0.7,
    api_key=GENAI_KEY
)


# Define Story styles and prompts (max 4–5 lines output expected)

def synthesize_text(text, output_path="output.mp3"):
    client = texttospeech.TextToSpeechClient()

    input_text = texttospeech.SynthesisInput(text=text)

    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name="en-US-Wavenet-D",
        ssml_gender=texttospeech.SsmlVoiceGender.MALE,
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )

    response = client.synthesize_speech(
        input=input_text, voice=voice, audio_config=audio_config
    )

    with open(output_path, "wb") as out:
        out.write(response.audio_content)
        print(f"✅ Audio content written to {output_path}")

def write_story_bottom_center(image_path: str, poem: str, output_path: str = None) -> str:
    """
    Writes multi-line wrapped text (poem or story line) to the bottom-center of an image
    with 10% horizontal padding and semi-transparent background.
    """
    from textwrap import wrap

    # Open image
    base_image = Image.open(image_path).convert("RGBA")
    width, height = base_image.size

    # Create overlay
    overlay = Image.new("RGBA", base_image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    # Load font
    try:
        font_path = "font/Esteban-Regular.ttf"
        font_size = width // 20
        font = ImageFont.truetype(font_path, font_size)
    except Exception as e:
        print(f"⚠️ Font load failed: {e}")
        font = ImageFont.load_default()
        font_size = font.getsize("A")[1]

    # Wrap text based on image width with 10% padding
    max_text_width = int(width * 0.8)  # 10% padding on each side
    wrapped_lines = []

    for line in poem.strip().split("\n"):
        wrapped_lines += wrap(line, width=40)  # fallback wrapping width
        # You could dynamically calculate based on textlength if needed

    spacing = int(font_size * 0.5)
    total_text_height = len(wrapped_lines) * (font_size + spacing)

    # Y position to start text block from
    y_start = height - total_text_height - int(height * 0.1)

    # Determine max width for background rectangle
    max_line_width = max(draw.textlength(line, font=font) for line in wrapped_lines)
    padding_x = int(width * 0.1)
    padding_y = 20

    rect_x0 = (width - max_line_width) / 2 - padding_x
    rect_y0 = y_start - padding_y
    rect_x1 = (width + max_line_width) / 2 + padding_x
    rect_y1 = y_start + total_text_height + padding_y

    # Draw translucent background
    draw.rectangle([(rect_x0, rect_y0), (rect_x1, rect_y1)], fill=(0, 0, 0, 128))

    # Draw text lines
    y = y_start
    for line in wrapped_lines:
        line_width = draw.textlength(line, font=font)
        x = (width - line_width) / 2
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += font_size + spacing

    # Merge and save
    combined = Image.alpha_composite(base_image, overlay)

    if not output_path:
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        output_path = os.path.join("STORY", f"{base_name}_poem.png")

    combined.convert("RGB").save(output_path)

    print(f"✅ Wrapped text written to: {output_path}")
    return output_path


#=========================================================================================================================================
#                    Image Generators 
#=========================================================================================================================================

# IMAGE GENERATOR Google Gemini FREE

def generate_image_from_prompt(prompt: str) -> str:
    """
    Generate an ultra-HD, clean image with no embedded text using Gemini API.
    Retries up to 3 times if quota is exceeded (429).
    """
    retries = 3
    for attempt in range(1, retries + 1):
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
                #model="gemini-2.0-flash-exp-image-generation",
                model="gemini-2.0-flash-preview-image-generation",
                contents=enhanced_prompt,
                config=types.GenerateContentConfig(response_modalities=['TEXT', 'IMAGE'])
            )

            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data is not None:
                    image = Image.open(BytesIO(part.inline_data.data))

                    # Optional: upscale if image is small
                    if image.width < 2000:
                        max_size = (2000, 2000)
                        image.thumbnail(max_size, Image.LANCZOS)

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = os.path.join("STORY", f"gemini_image_{timestamp}.png")
                    image.save(filename)
                    print(f"✅ UHD Image saved as {filename}")
                    return filename

            raise RuntimeError("❌ No image found in Gemini response.")

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "quota" in error_str:
                print(f"⚠️ Quota error (attempt {attempt}/3). Retrying in 5 seconds...")
                time.sleep(5)
            else:
                print(f"⚠️ Gemini image generation failed: {e}")
                break  # Don't retry on non-quota errors

    print("❌ Failed to generate image after 3 retries. Skipping.")
    raise RuntimeError("Image generation failed after 3 retries.")

#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#                                                          FFMPEG
#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
def combine_images_to_story_video(image_paths: list, audio_paths: list, frame_dir: str = "frames", duration_per_image: int = 3) -> str:
    import os, subprocess, random, json
    from pathlib import Path

    os.makedirs(frame_dir, exist_ok=True)
    mini_videos = []

    # Step 1: Create mini videos for each image + audio
    for i, (image_path, audio_path) in enumerate(zip(image_paths, audio_paths)):
        temp_video = os.path.join(frame_dir, f"scene_{i:03d}.mp4")
        mini_videos.append(temp_video)

        subprocess.run([
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image_path,
            "-i", audio_path,
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
            "-r", "30",
            temp_video
        ], check=True)

    # Step 2: Concatenate mini videos into story_video.mp4
    concat_list_path = os.path.join(frame_dir, "concat_list.txt")
    with open(concat_list_path, "w") as f:
        for path in mini_videos:
            f.write(f"file '{os.path.abspath(path)}'\n")

    story_video_path = os.path.join(frame_dir, "story_video.mp4")
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        story_video_path
    ], check=True)

    # Step 3: Add background music with narration
    music_dir = "music"
    bgm_files = [f for f in os.listdir(music_dir) if f.endswith(".mp3")]
    if not bgm_files:
        raise FileNotFoundError("No background music found in 'music/' directory.")
    bgm_path = os.path.join(music_dir, random.choice(bgm_files))

    final_output_with_bgm = os.path.join(frame_dir, "story_with_bgm.mp4")
    result = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json", story_video_path
    ], stdout=subprocess.PIPE)
    duration = float(json.loads(result.stdout)["format"]["duration"])
    fade_duration = 1.0

    subprocess.run([
        "ffmpeg", "-y",
        "-i", story_video_path,
        "-stream_loop", "-1",
        "-i", bgm_path,
        "-filter_complex",
        f"[0:a]volume=1.2[main];"
        f"[1:a]volume=0.65[bgm];"
        f"[main][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout];"
        f"[aout]afade=t=out:st={duration - fade_duration}:d={fade_duration}[finala];"
        f"[0:v]fade=t=out:st={duration - fade_duration}:d={fade_duration}[finalv]",
        "-map", "[finalv]", "-map", "[finala]",
        "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p",
        "-shortest",
        final_output_with_bgm
    ], check=True)

    # Step 4: Create silent 4s outro from finalLike.jpg (no audio)
    final_like_img = os.path.join(music_dir, "finalLike.jpg")
    final_like_video = os.path.join(frame_dir, "finalLike_fade.mp4")

    if not os.path.exists(final_like_img):
        raise FileNotFoundError("Missing 'finalLike.jpg' in music/")

    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", final_like_img,
        "-t", "5",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-an",  # <-- Disable audio
        final_like_video
    ], check=True)

    # Step 5: Final concatenation of video + silent outro
    final_concat_list = os.path.join(frame_dir, "final_concat.txt")
    with open(final_concat_list, "w") as f:
        f.write(f"file '{os.path.abspath(final_output_with_bgm)}'\n")
        f.write(f"file '{os.path.abspath(final_like_video)}'\n")

    final_output = os.path.join(frame_dir, "story_with_bgm_outro.mp4")
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", final_concat_list,
        "-c", "copy",
        "-movflags", "+faststart",
        final_output
    ], check=True)

    print(f"✅ Final story video with silent outro created: {final_output}")
    return final_output




def generate_caption_from_story(title: str) -> str:
     return (
        f"📖 *{title}*\n\n"
        
        '''
🎨✨ Step into a universe where imagination paints the skies and every frame tells a tale.
From heartwarming children’s wonders to breathtaking anime epics, each post is a portal into magic, mischief, and meaning.
🌈🖌️ Art isn’t just seen—it’s felt, lived, and dreamt.
Follow @toonocalypse and let your inner child take flight, your curiosity run wild, and your heart rediscover wonder. 🚀📖💫

🔖 Step into a world of #StoryArt, #DigitalStorytelling, and #VisualNarratives—where #AnimeStories, #MangaArt, and #AnimeIllustration meet #ImaginativeWorlds and #DreamscapeArt. From #WhimsicalArt to #NarrativeArt, every post is part of a #CreativeJourney and filled with #StorybookMagic and #AnimeInspiration. For dreamers of all ages: #GTA6 #ChildrensIllustration, #KidsStoryTime, and #InstaKids. Sharing #love, #photooftheday, #beautiful, #happy, #cute, and #picoftheday. Join the tale—#followme for more #Toonocalypse.'''
    )



def generate_tweet_from_story(story_arc: list, youtube_url: str = "", insta_url: str = "") -> str:
    """
    Returns:
    - tweet_caption: A tweet-safe caption that includes the story, CTA line, and both links, within 280 characters.
    """
    # Join the story into a poetic caption
    poem_clean = "\n".join(line.strip() for line in story_arc if line.strip())

    # CTA + links
    cta_line = '✨ Experience this story in cinematic art:\n'
    base_links = f"🎬 {youtube_url}\n📸 {insta_url}"
    reserved_length = len(cta_line + base_links)

    # Max characters available for the story part
    max_poem_chars = 280 - reserved_length

    # Trim poem if too long
    if len(poem_clean) > max_poem_chars:
        poem_clean = poem_clean[:max_poem_chars - 3].rstrip() + "..."

    # Final tweet caption
    tweet_caption = f"{poem_clean}\n{cta_line}{base_links}"
    return tweet_caption


#*****************************INSTAGRAM***Carosel**BEGIN***********************************


#*****************************INSTAGRAM***Media**BEGIN***********************************
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
            "categoryId": "22"
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

    #print(f"✅ Uploaded to YouTube: https://youtu.be/{response['id']}")
    return response["id"]

#********************************Youtube End**************************************************************
def post_to_twitter_text_only(caption: str) -> str:
    """
    Post a text-only tweet using Twitter API v2 (Free tier compliant).
    """
    try:
        client = tweepy.Client(
            bearer_token=os.getenv("TWITTER_BEARER_TOKEN"),
            consumer_key=os.getenv("TWITTER_API_KEY"),
            consumer_secret=os.getenv("TWITTER_API_SECRET"),
            access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
            access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
        )

        response = client.create_tweet(text=caption[:280])
        tweet_id = response.data["id"]
        print(f"✅ Tweet Successful https://twitter.com/user/status/{tweet_id}")
        return f"https://twitter.com/user/status/{tweet_id}"
    
    except Exception as e:
        print(f"⚠️ Twitter text post failed: {e}")
        return ""

        return ""
#********************************Twitter End**************************************************************
'''
def add_watermark_to_image(image_path: str, text: str = "@poeminpixels", position: str = "bottom_right") -> str:
    """
    Adds a larger, semi-transparent watermark to the image for visibility in social media.
    """
    try:
        image = Image.open(image_path).convert("RGBA")
        watermark_layer = Image.new("RGBA", image.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(watermark_layer)

        width, height = image.size
        font_size = width // 20  # Increased from 1/40 to 1/20 of image width

        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        margin = int(font_size * 0.5)
        if position == "bottom_right":
            x = width - text_width - margin
            y = height - text_height - margin
        elif position == "bottom_left":
            x = margin
            y = height - text_height - margin
        else:  # center
            x = (width - text_width) // 2
            y = height - text_height - margin

        draw.text((x, y), text, font=font, fill=(255, 255, 255, 200))  # More visible

        combined = Image.alpha_composite(image, watermark_layer)
        output_path = os.path.splitext(image_path)[0] + "_watermarked.png"
        combined.convert("RGB").save(output_path)
        print(f"✅ Watermark added: {output_path}")
        return output_path

    except Exception as e:
        print(f"⚠️ Failed to add watermark: {e}")
        return image_path
'''


def generate_consistent_background(story_arc):
    """Generates one vivid, consistent background for the entire story arc, ignoring cameo characters."""
    print("\n🧠 Generating consistent scenic base...")
    bg_prompt_msg = [
        SystemMessage(content="You are an AI visual designer."),
        HumanMessage(content=(
            f"Given this story:\n{chr(10).join(story_arc)}\n\n"
            "Ignore any individual characters or cameo appearances. "
            "Focus only on describing a consistent background *setting* "
            "(natural, urban, fantasy, sci-fi, etc.) that fits the overall story arc. "
            "Use no more than 20 words. Do not reference characters or actions."
        ))
    ]
    bg_description = llm.invoke(bg_prompt_msg).content.strip()
    print(f"🪷 Consistent Background: {bg_description}")
    return bg_description

def generate_character_profile(story_arc: list, hero_profile: str = "Cranktail") -> str:
    """
    Generate character descriptions for animation design based on story and a specified hero.
    Includes the main hero's profile in the prompt; lets LLM invent side characters.
    """

    try:
        
        # Prepare hero profile string for prompt
        hero_profile_str = "\n".join(f"- {key}: {value}" for key, value in hero_profile.items())

        # Compose prompt
        prompt = (
            f"You are designing characters for an animated film.\n\n"
            f"Main Hero Profile:\n{hero_profile_str}\n\n"
            f"Story Scenes:\n" +
            "\n".join(f"- {scene}" for scene in story_arc) +
            "\n\nBased on the above, describe all characters in max 150 characters.The characters should be divided into two sections:\n"
            "**1. Main Character(s):**\n"
            "Include the described hero with physical traits, species, clothing, color palette, etc.\n"
            "**2. Side Character(s):**\n"
            "Include other significant characters needed by the story arc.\n\n"
            "Descriptions must be clear, vivid, and animation-ready. Focus on physical appearance and clothing"
        )

        msgs = [
            SystemMessage(content="You are a professional character designer for animated films. Your job is to create clear, vivid, and consistent visual character descriptions."),
            HumanMessage(content=prompt)
        ]

        response = llm.invoke(msgs).content.strip()
        print(f"🎨 Character profile:\n{response}")
        return response

    except Exception as e:
        print(f"⚠️ Character profile generation failed: {e}")
        return ""


# Refactored story arc generation with strong structure

def generate_story_arc(hero_profile: dict, story_idea: str) -> list:
    """
    Generates a cinematic action-comedy story arc (8–15 scenes) with viral hooks in the first 3 scenes.
    Tailored for short-form video platforms (Instagram Reels, YouTube Shorts).
    """
    if not story_idea or not hero_profile:
        print("⚠️ Missing hero profile or story idea.")
        return []

    hero_name = hero_profile.get("name", "The Hero")
    print(f"🎬 Generating story arc for hero: {hero_name}")
    print(f"💡 Story Idea: {story_idea}")

    hero_profile_str = "\n".join(f"- {k.capitalize()}: {v}" for k, v in hero_profile.items())

    instruction = (
        f"Write a complete animated short story in 8 to 15 cinematic scenes.\n"
        f"Main Character:\n{hero_profile_str}\n"
        f"Story Idea:\n- {story_idea}\n\n"
        f"Instructions:\n"
        f"- First 3 scenes MUST be highly visual, emotionally intense, or funny — true hooks for Instagram Reels or YouTube Shorts.\n"
        f"- Examples of hook types: unexpected action, weird behavior, wild character twist, mystery item, or comic blunder.\n"
        f"- Use visual storytelling. Treat each scene like a movie frame — camera-ready and surprising.\n"
        f"- Each scene should be a single sentence, no more than 15 words.\n"
        f"- Use plain, punchy, kid-friendly language. No rhyming or poetic fluff.\n"
        f"- Hero should appear in most scenes.\n"
        f"- No numbering, no scene titles, no summaries. Just 1 sentence per line.\n"
        f"- Style: action-comedy, light-hearted, Pixar-style clarity, viral pacing.\n"
        f"- Avoid detailed backstories or slow intros. Start in the middle of action.\n"
    )

    msgs = [
        SystemMessage(content="You are a top-tier animated short scriptwriter for Reels and Shorts."),
        HumanMessage(content=instruction)
    ]

    try:
        response = llm.invoke(msgs).content.strip()
        lines = [line.strip("-•* ").strip() for line in response.split("\n") if line.strip()]
        clean_lines = [
            l for l in lines
            if len(l.split()) > 3 and not re.match(r'^\(*scene|part|frame|title|chapter', l, re.IGNORECASE)
        ]

        return clean_lines

    except Exception as e:
        print(f"⚠️ Story arc generation failed: {e}")
        return []



def clean_scene_lines(story_arc):
    cleaned = []
    for line in story_arc:
        # Remove labels like Opener:, Visual:, Emotion:, etc.
        line = re.sub(r"^\s*(\*+)?\s*(Opener|Final Moment|Visual|Tension/Conflict|Emotion|Reflection)\s*[:：]*\s*", "", line, flags=re.IGNORECASE)
        line = re.sub(r"^\(Visual:\s*", "", line, flags=re.IGNORECASE)
        line = re.sub(r"\)$", "", line.strip())  # remove closing parenthesis if present
        cleaned.append(line.strip())
    return cleaned


def llm_clean_story_arc_labels(story_arc: list) -> list:
    """
    Uses LLM to clean a visual story arc without altering story content.
    - Removes visual/narrative labels (like Opener, Visual, Scene 2, etc.)
    - Removes unnecessary parentheticals (e.g., (a mischievous grin))
    - Renames famous characters with funny rhyming names (e.g., Batman → Flatman)
    - Keeps original story content and structure unchanged
    """
    full_story = "\n".join(f"{i+1}. {s}" for i, s in enumerate(story_arc))

    prompt = (
        "You're a clever formatting assistant for animated children's stories.\n"
        "Each line is a scene. Only do the following:\n"
        "- ❌ Remove visual or structure labels like (Visual:), Opener:, Emotion:, Scene 2:, etc.\n"
        "- ❌ Remove parentheticals like (a mischievous grin), (Final moment), etc.\n"
        "- ✅ Rename any famous character (e.g., Batman → Flatman, Elsa → Meltza) to a playful, rhyming version\n"
        "- 🛑 Do NOT change any wording or structure of the story\n"
        "- 🛑 Do NOT rewrite or simplify sentences\n"
        "- ✅ Keep one cleaned scene per line, numbered exactly like the input\n"
        "\nNow clean the following story:\n\n"
        f"{full_story}"
    )

    system_msg = (
        "You clean up story formatting only — you remove labels, remove parentheticals, and rename famous characters.\n"
        "You do not change any storytelling, sentence structure, or scene content."
    )

    msgs = [SystemMessage(content=system_msg), HumanMessage(content=prompt)]

    try:
        response = llm.invoke(msgs).content.strip()

        import re
        matches = re.findall(r"\d+\.\s*(.+)", response)
        cleaned_scenes = [m.strip() for m in matches]

        if len(cleaned_scenes) != len(story_arc):
            print(f"⚠️ Scene count mismatch: expected {len(story_arc)}, got {len(cleaned_scenes)}. Returning original.")
            return story_arc

        return cleaned_scenes

    except Exception as e:
        print(f"⚠️ LLM cleaning failed: {e}")
        return story_arc


def generate_scenes_from_story(
    story_arc,
    bg_description,
    character_description,
    mode: str = "cinematic",
    frame_dir: str = "frames"
):
    image_paths = []
    audio_paths = []

    story_arc = clean_scene_lines(story_arc)

    narration_arc = llm_clean_story_arc_labels(story_arc)
    print(f"\n\n\n🎙️ Narration Arc:\n{narration_arc}")
    print("\n📖 Narration Story:---------->")
    for line in narration_arc:
        print(" -", line)

    for i, (scene, narration_line) in enumerate(zip(story_arc, narration_arc)):
        print(f"\n🎬 Scene {i+1}: {scene}")

        # Step 1: Ask LLM which characters are in the scene
        try:
            scene_character_msg = [
                SystemMessage(content=(
                    "You are an animation script analyst.\n"
                    "You will receive a character profile followed by a scene description.\n"
                    "Your job is to identify which characters are present or mentioned(directly or indirectly) in the scene, "
                    "and summarize their visual role briefly. In case of doubt, include as many as possible."
                )),
                HumanMessage(content=(
                    f"Character Profile:\n{character_description.strip()}"
                )),
                HumanMessage(content=(
                    f"Scene:\n{scene.strip()}\n\n"
                    "List only the characters (main or side) that clearly appear or are mentioned in this scene. "
                    "Return a short paragraph summarizing their visual role or presence."
                ))
            ]
            relevant_characters = llm.invoke(scene_character_msg).content.strip()
            print(f"🧍 Characters present in scene {i+1}: {relevant_characters}")
        except Exception as e:
            print(f"⚠️ Character detection failed: {e}")
            relevant_characters = "Main character and any obvious side characters present in the scene."

        # Step 2: Merge prompt with background and filtered characters
        merged_prompt_msg = [
            SystemMessage(content="You are a prompt engineer for AI image generation."),
            HumanMessage(content=(
                f"Background: {bg_description}\n\n"
                f"Character Design Guide:\n{character_description.strip()}\n\n"
                f"Characters present in this scene: {relevant_characters.strip()}\n\n"
                f"Action: {scene.strip()}\n\n"
                "Generate a cinematic vertical image (Pixar/DreamWorks style) based on this setup. "
                "Use the full character design guide to render each character consistently. "
                "No photorealism. No text or labels. High visual storytelling impact."
            ))
        ]


        try:
            scenic_prompt = llm.invoke(merged_prompt_msg).content.strip()
            if "please provide" in scenic_prompt.lower() or len(scenic_prompt) < 10:
                raise ValueError("Invalid scenic prompt received from LLM.")
            print(f"🖼️ Prompt: {scenic_prompt}")
        except Exception as e:
            print(f"⚠️ Scenic prompt generation failed at scene {i+1}: {e}")
            continue

        try:
            animated_prompt = (
                f"{scenic_prompt.strip()}\n\n"
                "Generate a high-resolution animated-style illustration. "
                "The image should be cinematic, painted or stylized, like from a Pixar or DreamWorks movie. "
                "Use soft lighting, expressive composition, and warm color tones. No photorealism. No text or labels."
                "Give strong expressions to the characters according to the story."
            )

            # Step 3: Generate image
            base_image_path = generate_image_from_prompt(animated_prompt)

            # Step 4: Vertical frame conversion
            #reel_frame_path = make_instagram_reel_frame(base_image_path)

            # Step 5: Add narration text to image
            final_image_path = os.path.join(frame_dir, f"frame{i:03d}.png")
            write_story_bottom_center(base_image_path, poem=narration_line, output_path=final_image_path)
            image_paths.append(final_image_path)

            # Step 6: Voiceover
            audio_path = os.path.join("voiceovers", f"line{i}.mp3")
            synthesize_text(narration_line, audio_path)
            audio_paths.append(audio_path)

        except Exception as e:
            print(f"⚠️ Failed to generate scene {i+1}: {e}")
            continue

    return image_paths, audio_paths



def generate_title_from_story(story: list[str]) -> str:
    """
    Uses LLM to generate a short, emotionally engaging title from a list of story lines.
    Returns a clean, one-line title only — no explanation or variants.
    """
    if not story or not isinstance(story, list):
        print("⚠️ Invalid story format. Expected a non-empty list of lines.")
        return "A Magical Story"

    story_text = "\n".join(f"- {line.strip()}" for line in story if line.strip())

    try:
        prompt = [
            SystemMessage(content="You are a poetic storyteller and title expert."),
            HumanMessage(content=(
                f"Based on the story below, generate one short, emotionally engaging and imaginative title.\n"
                f"Return only the title — no quotes, no explanation, no alternatives.\n\n"
                f"{story_text}"
            ))
        ]
        title = llm.invoke(prompt).content.strip()
        title = re.sub(r'[^\w\s\-:]', '', title)  # Clean for safe display
        return title
    except Exception as e:
        print(f"⚠️ Title generation failed: {e}")
        return "A Magical Story"


if __name__ == "__main__":
    try:
        OUTPUT_DIR = "STORY"
        FRAME_DIR = "frames"
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        os.makedirs(FRAME_DIR, exist_ok=True)
        
        # Remove FRAME_DIR if it exists, then recreate
        if os.path.exists(FRAME_DIR):
            shutil.rmtree(FRAME_DIR)
        os.makedirs(FRAME_DIR)

        mode = "cinematic" #viral_simple cinematic

        selected_hero = random.choice(heroes)
        selected_story = random.choice(action_story)
        print(f"🦸 Hero: {selected_hero['name']}")
        print(f"🎬 Selected Story: {selected_story}")

        # Use action-based random story + hero system
        story_arc = generate_story_arc(selected_hero, selected_story)
        story_title = generate_title_from_story(story_arc)

        print(f"\n story_title: {story_title}")
        print(f"\n story_arc: {story_arc}")
        
        if not story_arc or len(story_arc) < 3:
            max_retries = 3
            retry_count = 0

            while (not story_arc or len(story_arc) < 3) and retry_count < max_retries:
                selected_hero = random.choice(heroes)
                selected_story = random.choice(action_story)
                print(f"🦸 Hero: {selected_hero['name']}")
                print(f"🎬 Selected Story: {selected_story}")

                # Use action-based random story + hero system
                story_arc = generate_story_arc(selected_hero, selected_story)
                story_title = generate_title_from_story(story_arc)

                print(f"\n story_title: {story_title}")
                print(f"\n story_arc: {story_arc}")

                retry_count += 1

            if not story_arc or len(story_arc) < 3:
                print("❌ Failed to generate a valid story arc after 3 retries.")
                # Optionally raise an error or exit the program here
                raise Exception("Story arc generation failed.")
            else:
                print("✅ Successfully generated story arc.")
                # Continue with processing story_arc

        if not story_arc:
            raise RuntimeError("Story arc generation failed.")

        print("\n📖 Visual Story:")
        for line in story_arc:
            print(" -", line)

        bg_description = generate_consistent_background(story_arc)
        character_description = generate_character_profile(story_arc,selected_hero)

        image_paths, audio_paths = generate_scenes_from_story(
            story_arc, bg_description, character_description, mode=mode, frame_dir=FRAME_DIR
        )
        
        # 0. Make Video
        story_video = combine_images_to_story_video(image_paths, audio_paths,FRAME_DIR, duration_per_image=3)
        print(f"\n✅ Story video created: {story_video}")
        
        
        # 1. Generate caption
        caption = generate_caption_from_story(story_title)
        print(f"✅ Caption: {caption}")
        
        # 2. Publish to Youtube
        yt_id = upload_video_to_youtube(video_path=story_video, title=story_title, description=caption, tags=["visual story", "animated tale", "kids", "storytelling", "pixar style", "short film"])
        print(f"✅ YouTube Shorts uploaded: https://youtu.be/{yt_id}")
        
        # 3. Post Reel
        print("🎬 Mode selected: Instagram Reel")
        post_reel(story_video, caption)
        print("✅ Reel uploaded to Instagram.")
        
        # 5. Publish to Twitter (X)
        yt_url = f"https://youtu.be/{yt_id}" if 'yt_id' in locals() else ""
        insta_url = "https://www.instagram.com/toonocalypse/"  # replace with your real profile link
        tweet_caption = generate_tweet_from_story(story_arc, yt_url, insta_url)

        # 3. Post to Twitter (text only)
        tweet_url = post_to_twitter_text_only(tweet_caption)
                
    except Exception as e:
        print(f"⚠️ Failed to generate visual story: {e}")
