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
from google.cloud import aiplatform
from google.cloud import aiplatform_v1beta1
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Value
from datetime import datetime
from google_auth_oauthlib.flow import InstalledAppFlow
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


# YouTube OAuth scope and token endpoint
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"


# Load API key from .env
load_dotenv()

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

# Cloudinary config (make sure these are in your .env file)
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

def upload_to_cloudinary(local_path: str) -> str:
    try:
        result = cloudinary.uploader.upload(local_path)
        url = result.get("secure_url")
        print(f"✅ Cloudinary upload success: {url}")
        return url
    except Exception as e:
        print(f"❌ Cloudinary upload failed for {local_path}: {e}")
        return ""



# Define Story styles and prompts (max 4–5 lines output expected)
story_styles = {
  "Whimsical": [
    "a fox who learns to skate on rainbows",
    "a kitten building a tiny hot-air balloon",
    "a hedgehog discovering musical bubbles",
    "a child who befriends a dancing lantern",
    "a squirrel hosting a tea party under mushrooms",
    "a rabbit who paints flowers on raindrops",
    "a toddler chasing giggling fireflies",
    "a puppy who bakes glow-in-the-dark cookies",
    "a mouse conducting an orchestra of crickets",
    "a child shrinking to play with toy dinosaurs",
    "a cat who floats on a soap-bubble cloud",
    "a bird teaching sky-writing to butterflies",
    "a snail racing on a trail of stardust",
    "a baby giraffe learning to paint portraits",
    "a child trading crayons with a chameleon",
    "a kitten who rides a dragonfly taxi",
    "a mouse who writes love letters to the moon",
    "a toddler discovering a secret candy tree",
    "a baby elephant juggling dewdrops",
    "a child solving puzzles inside a snow globe",
    "a kitten selling umbrellas to dancing snails",
    "a child and a fox planting smiling sunflowers",
    "a hedgehog who flies on a giant dandelion",
    "a rabbit teaching yoga to garden gnomes",
    "a child who organizes a cloud-parade"
  ],

  "Comedy": [
    "a goat who steals everyone’s slippers",
    "a clumsy penguin trying to tap-dance",
    "a kitten mistaking yarn for spaghetti",
    "a child whose sandwich keeps escaping",
    "a dog who delivers mail to the wrong houses",
    "a squirrel trying to juggle acorns",
    "a grandma racing a robotic vacuum",
    "a parrot imitating every ringtone it hears",
    "a toddler swapping shoes with the cat",
    "a raccoon dumpster-diving for pizza",
    "a hamster hosting a courtroom trial",
    "a baby goat stranded on a trampoline",
    "a kid trying to teach a fish to fetch",
    "a bear who thinks it’s a ballet dancer",
    "a puppy getting stuck in a party hat",
    "a child hiding broccoli in the dog’s bowl",
    "a squirrel giving motivational speeches",
    "a parrot heckling its own reflection",
    "a child building a wobbly tower of pancakes",
    "a mouse wearing oversized sunglasses",
    "a kitten photobombing every selfie",
    "a toddler stuck in a giant cardboard box",
    "a dog trying to bark opera",
    "a cat interrupting a Zoom meeting",
    "a child slipping on banana peels"
  ],

  "Toys": [
    "a teddy bear who climbs a bookshelf mountain",
    "a toy train chasing runaway marbles",
    "a doll who paints a rainbow mural",
    "a toy soldier rescuing a fallen toy car",
    "a wind-up rabbit racing a jack-in-the-box",
    "a teddy bear teaching yoga to plush friends",
    "a toy giraffe stuck in a dollhouse window",
    "a building block castle under siege by Legos",
    "a plush shark learning to swim in a fish tank",
    "a toy rocket blasting off from a desk lamp",
    "a doll hosting a fashion show for action figures",
    "a stuffed fox delivering messages to dolls",
    "a wind-up mouse playing hide-and-seek",
    "a toy dinosaur discovering a jungle of plants",
    "a plush llama riding a toy train",
    "a puzzle piece feeling lost—and then found",
    "a toy robot learning to draw hearts",
    "a dollhouse garden growing real flowers",
    "a plush turtle teaching naptime meditation",
    "a jack-in-the-box throwing surprise parties",
    "a toy lion leading a parade of stuffed friends",
    "a race between a toy car and a wind-up snail",
    "a wooden horse learning to moonwalk",
    "a plush puppy opening a miniature bakery",
    "a doll writing postcards to the moon"
  ],

  "Fantasy": [
    "a dragon teaching a village to fly kites",
    "a unicorn painting clouds at dawn",
    "a young wizard turning leaves into butterflies",
    "a fairy hosting a starlight tea party",
    "a talking cat guiding heroes through mirrors",
    "a child discovering a floating crystal library",
    "a griffin rescuing lost dreamers",
    "a mermaid building sandcastles at midnight",
    "a goblin trading gold for giggles",
    "a knight befriending a three-headed puppy",
    "a pixie composing symphonies with lightning",
    "a tree that grants wishes to travelers",
    "a child riding a giant owl messenger",
    "a sorcerer’s apprentice painting the sunrise",
    "a phoenix nursing a wounded sparrow",
    "a dwarf finding a glowing cave of memories",
    "a child watering whispering flower vines",
    "a dragon hatchling learning to roar lullabies",
    "a magical map leading to friendship",
    "a child and a sprite rebuilding a ruined tower",
    "a centaur coaching a rabbit race",
    "a wizard’s hat teaching jokes at midnight",
    "a child unlocking dreams with a silver key",
    "a mermaid and mouse sharing sea­glass treasures",
    "a fairy doctor healing wounded fireflies"
  ],

  "Moon": [
    "a rabbit harvesting moonbeam carrots",
    "a child sliding down a crescent moon",
    "bunnies hosting a glow-in-the-dark hopscotch",
    "the moon painting meteors into butterflies",
    "a star learning to blink in rhythm",
    "a child sending wishes via moonlight mail",
    "a fox stargazing with lunar telescope",
    "a moon-sheep grazing on stardust fields",
    "a kitten knitting moonbeam scarves",
    "a child and a cricket singing lullabies to stars",
    "a moon gardener planting comet seeds",
    "bats dancing under a silver spotlight",
    "a teddy bear camping in a moon crater",
    "a child fishing for shooting stars",
    "a raccoon riding a moonrock buggy",
    "a sheep counting humans instead of sheep",
    "a child hosting a moonlight puppet show",
    "an owl delivering moon poems at midnight",
    "a moonfox chasing lunar moths",
    "a child painting moon phases with watercolor",
    "a baby dragon hatching under starlight",
    "a child and a bat playing hide-and-seek",
    "a moon librarian cataloguing crater craters",
    "a kitten chasing moon shadows",
    "a child sharing cookies with moon sprites"
  ],

  "Kids": [
    "a group building a cardboard rocket ship",
    "a child trading chores for magical stickers",
    "kids solving a candy mystery",
    "a drawing that steps off the page",
    "a backyard turned into pirate bay",
    "kids racing homemade soapbox cars",
    "a child making friends with a sidewalk chalk dragon",
    "a group planting wishes in a wishing tree",
    "a kid baking mud pies in a pretend bakery",
    "a hide-and-seek game with garden gnomes",
    "a child discovering a secret attic portal",
    "kids hosting a living-room carnival",
    "a pillow fort that becomes a castle",
    "a child teaching ants to march",
    "kids starting a neighborhood kindness club",
    "a child trading stickers for giggles",
    "a group painting a rainbow on a grey wall",
    "a kid and a puppy learning to skateboard",
    "kids creating a cloud museum",
    "a child befriending a ladybug orchestra",
    "kids following a treasure map in the park",
    "a child swapping dreams with a tree",
    "kids assembling a time-capsule picnic",
    "a child unveiling a magic door in the sandbox",
    "kids racing balloon-powered boats"
  ],

  "Sci-Fi": [
    "a cat repairing a tiny robot heart",
    "a child growing plants in zero-gravity",
    "a robot learning to paint sunsets",
    "a dog delivering messages across galaxies",
    "a group of kittens programming a spaceship",
    "a robot befriending an alien sparrow",
    "a child decoding star-ry hieroglyphs",
    "a hamster piloting a micro-shuttle",
    "a space whale guiding lost travelers",
    "a robot DJ remixing comet tails",
    "a fox hacking cosmic traffic lights",
    "a child planting solar-powered flowers",
    "a drone rescuing stranded fireflies",
    "a robot making friends with asteroid mice",
    "a child and a robot racing solar kites",
    "a puppy exploring a neon-lit asteroid",
    "a robot dancer under hologram stars",
    "a child hacking lunar rover circuits",
    "a robo-dog teaching human tricks",
    "a kitten activating a starlight beacon",
    "a child and AI tea party on Mars",
    "a robot delivering moon cheese to bunnies",
    "a puppy solving a zero-G maze",
    "a bot building a miniature Earth",
    "a child mapping rainbow wormholes"
  ],

  "Inspirational": [
    "a rescued puppy learning to trust again",
    "a child climbing a “mountain of fears”",
    "a squirrel gathering acorns for all friends",
    "a dog guiding a lost traveler home",
    "a kitten finding courage to meow loudly",
    "a child painting hope on community walls",
    "a turtle finishing a huge race at its own pace",
    "a child teaching a dragon kindness",
    "a rabbit persevering through a long tunnel",
    "a fox sharing food with forest friends",
    "a child building a bridge between islands",
    "a bird teaching other animals to sing",
    "a puppy comforting a crying child",
    "a child repairing a broken swing for everyone",
    "a hedgehog helping a snail cross a road",
    "a child planting a forest of dreams",
    "a kitten rescuing stranded ducklings",
    "a child and a cloud learning to share rain",
    "a squirrel rebuilding a fallen nest",
    "a child cheering up lonely robots",
    "a dog inspiring its puppy siblings to leap",
    "a child giving away glowing stones of happiness",
    "a fox paving a path for lost fireflies",
    "a child teaching fish to leap waterfalls",
    "a rabbit planting carrots for every neighbor"
  ],

  "Talking Trees": [
    "a tree teaching a child to listen to wind secrets",
    "forest trees singing lullabies to seedlings",
    "a tree guiding a lost puppy home",
    "trees exchanging stories with migrating birds",
    "a sapling sharing dreams with a child",
    "a tree and a fox swapping wisdom",
    "trees holding council to save a river",
    "a tree cheering on a snail race",
    "forest sentinels protecting a wounded deer",
    "trees weaving hammocks for forest friends",
    "a child whispering wishes into tree bark",
    "a tree sending acorn letters to squirrels",
    "talking roots comforting anxious seedlings",
    "a tree and a child painting sunset silhouettes",
    "forest elders teaching mushrooms to glow",
    "a tree hosting midnight star-gazing",
    "saplings hiding giggles under leaves",
    "a tree guiding fireflies to safety",
    "forest poets reciting sunrise odes",
    "a child planting seeds after tree lessons",
    "a tree singing birds awake at dawn",
    "roots healing broken woodland paths",
    "a tree and a kitten sharing naps",
    "forest sentries rallying for spring",
    "a child carving kindness symbols in bark"
  ],

  "Adventure": [
    "a fox mapping secret forest trails",
    "a child discovering a hidden waterfall cave",
    "a squirrel treasure-hunting for golden acorns",
    "a puppy rafting down a rainbow river",
    "a rabbit exploring an abandoned windmill",
    "a kitten charting the attic’s secret rooms",
    "a child climbing a giant sunflower stalk",
    "a turtle sailing on a leaf-boat across a pond",
    "a hedgehog spelunking glowing crystal caves",
    "a child following a dragonfly convoy",
    "a raccoon navigating city rooftops",
    "a child finding a pirate’s old telescope",
    "a fox and puppy crossing a rickety bridge",
    "a child unearthing fossilized starfish",
    "a kitten scaling a library’s book-tower",
    "a child and bird mapping cloud islands",
    "a squirrel trekking to the top of oak hill",
    "a child racing a wild stallion in dreams",
    "a rabbit discovering moonlight trails",
    "a child diving for rainbow pearls",
    "a kitten leading a night-time expedition",
    "a child and fox unlocking ancient runes",
    "a puppy crossing a field of living flowers",
    "a child finding a map inside a seashell",
    "a raccoon returning treasure to forest friends"
  ],

  "Cars": [
    "a puppy converting a toy car into a rocket",
    "a kitten racing a remote-control drift car",
    "a child fixing a broken bicycle caravan",
    "a fox autobahn race with tumbleweed spectators",
    "a toddler driving a cardboard taxi",
    "a raccoon tuning an old ice-cream truck",
    "a child and dog hosting a soapbox derby",
    "a kitten building a pedal-powered camper",
    "a child navigating a maze of wheel tracks",
    "a fox hitchhiking on toy trucks",
    "a baby elephant learning to steer a jeep",
    "a child painting cars to look like animals",
    "a puppy street-racing glow-sticks at dusk",
    "a kitten organizing a parade of toy buses",
    "a raccoon painting stripes on a skateboard",
    "a child teaching ants to pull a matchbox car",
    "a puppy delivering letters by scooter",
    "a child escaping boredom in a leaf-carriage",
    "a fox teaching road safety to forest critters",
    "a toddler steering a rolling pumpkin",
    "a kitten drifting through piles of leaves",
    "a child racing clouds in a cardboard car",
    "a puppy barking directions in a scavenger hunt",
    "a fox customizing a toy monster truck",
    "a child surveying neighborhood in wagon convoy"
  ],

  "Robot": [
    "a kitten befriending a rusty helper bot",
    "a child teaching a robot to tell jokes",
    "a puppy charging solar-powered drone wings",
    "a child and bot planting digital flowers",
    "a robot learning to paint watercolor skies",
    "a toddler giving a bot a teddy bear hug",
    "a robot composing lullabies for toys",
    "a child rescuing a stranded rover",
    "a puppy racing a mechanical hare",
    "a robot reading bedtime stories to kids",
    "a child fixing a bot’s squeaky wheel",
    "a robot helping a mouse build a house",
    "a kitten hiding from a ticklish cleaning bot",
    "a child and bot sharing ice-cream data",
    "a robot leading a parade of wind-up toys",
    "a puppy teaching a robot to fetch",
    "a child and bot dancing under LED stars",
    "a robot delivering flowers to forest friends",
    "a kitten reprogramming a toy soldier",
    "a robot painting kindness messages on walls",
    "a child and bot unearthing buried treasure",
    "a robot learning to purr like a cat",
    "a puppy guiding a bot through puzzles",
    "a child teaching a robot to plant seeds",
    "a robot cheering up a lonely hedgehog"
  ],

  "Romance": [
    "a cat delivering love notes between friends",
    "a child giving a flower to a shy puppy",
    "two foxes sharing a moonlit picnic",
    "a child and bird exchanging lullabies",
    "a rabbit building a heart-shaped burrow",
    "a child sewing a quilt for a sick kitten",
    "two turtles racing to ring a forest bell",
    "a child sharing cookies with a lonely dog",
    "a kitten and puppy holding paws at sunrise",
    "a child painting portraits for neighbors",
    "two squirrels exchanging acorns of promise",
    "a child and parrot whispering secrets",
    "a fox wrapping a scarf around a hedgehog",
    "a child writing poems in sand for a friend",
    "two baby turtles hatching side by side",
    "a child giving a hug to a crying bunny",
    "a kitten and robin trading songs",
    "a child rescuing a stranded firefly duo",
    "two bunnies weaving wreaths together",
    "a child sharing dreams with a puppy",
    "two mice building a heart-shaped cheese house",
    "a child planting a rose for someone special",
    "two baby birds learning to fly together",
    "a child and fox finding love-shaped footprints",
    "a kitten delivering heart-shaped cookies"
  ],

  "Animals": [
    "a stray dog finding a colorful new home",
    "jungle animals teaming to save a sapling",
    "a kitten with a secret nighttime mission",
    "a raccoon learning to share acorns",
    "animals rescuing their zookeeper",
    "a rabbit who paints secret murals",
    "a baby elephant learning to trumpet tunes",
    "a kitten comforting a scared turtle",
    "a fox guiding lost chicks home",
    "a puppy teaching wolves to wag tails",
    "a squirrel organizing a nut festival",
    "a baby panda discovering bamboo art",
    "a cat coaching mice to dance safely",
    "a hedgehog healing a wounded bird",
    "a duckling leading a pond parade",
    "a kitten and puppy planting sunflower seeds",
    "a baby giraffe painting sky-high murals",
    "a raccoon restoring a forest library",
    "a fox helping otters build a dam",
    "a puppy teaching kittens to fetch",
    "a monkey sharing bananas with friends",
    "a kitten writing letters for hamsters",
    "a baby owl learning to hoot lullabies",
    "a duck guiding ducklings across a rainbow bridge",
    "a squirrel building homes for homeless hedgehogs"
  ]
}


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
#                                                          Scene writers
#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
def combine_images_to_story_video(image_paths: list, audio_paths: list, frame_dir: str = "frames", duration_per_image: int = 3) -> str:
    os.makedirs(frame_dir, exist_ok=True)
    mini_videos = []

    # Step 1: Create mini videos for each image and corresponding narration
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

    # Step 2: Create a file list for concatenation
    concat_list_path = os.path.join(frame_dir, "concat_list.txt")
    with open(concat_list_path, "w") as f:
        for path in mini_videos:
            f.write(f"file '{os.path.abspath(path)}'\n")

    # Step 3: Concatenate mini videos into a single story video
    final_output = os.path.join(frame_dir, "story_video.mp4")
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        final_output
    ], check=True)

    # Step 4: Select a random background music file from the 'music' directory
    music_dir = "music"
    bgm_files = [f for f in os.listdir(music_dir) if f.endswith(".mp3")]
    if not bgm_files:
        raise FileNotFoundError("No MP3 files found in the 'music' directory.")
    bgm_path = os.path.join(music_dir, random.choice(bgm_files))

    # Step 5: Merge background music with the story video
    #         - Use filter_complex to mix audio
    #         - Apply fade-out to the end of the video and audio
    final_output_with_bgm = os.path.join(frame_dir, "story_with_bgm.mp4")

    # First get duration of the final_output
    
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "json", final_output
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    duration = float(json.loads(result.stdout)["format"]["duration"])
    fade_duration = 3  # duration of fade-out
    subprocess.run([
        "ffmpeg", "-y",
        "-i", final_output,         # narration video with audio
        "-stream_loop", "-1",
        "-i", bgm_path,             # background music
        "-filter_complex",
        f"[0:a]volume=1.2[main];"                                 # boost narration
        f"[1:a]volume=0.75[bgm];"                                 # reduce BGM
        f"[main][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout];"
        f"[aout]afade=t=out:st={duration - fade_duration}:d={fade_duration}[finala];"
        f"[0:v]fade=t=out:st={duration - fade_duration}:d={fade_duration}[finalv]",
        "-map", "[finalv]",
        "-map", "[finala]",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-shortest",
        final_output_with_bgm
    ], check=True)


    # Step 6: Create a 4-second video from finalLike.png with fade-in and fade-out
    final_like_image = os.path.join(music_dir, "finalLike.png")
    if not os.path.exists(final_like_image):
        raise FileNotFoundError("Missing 'finalLike.png' in 'music' directory.")

    final_like_video = os.path.join(frame_dir, "finalLike_fade.mp4")
    final_like_duration = 4  # Total: 1s fade-in + 2s hold + 1s fade-out

    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", final_like_image,
        "-t", str(final_like_duration),
        "-vf",
        (
            "format=yuva420p,"
            "fade=t=in:st=0:d=1:alpha=1,"
            "fade=t=out:st=3:d=1:alpha=1,"
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
        ),
        "-r", "30",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        final_like_video
    ], check=True)

    # Step 7: Concatenate story_with_bgm and finalLike_fade.mp4
    final_concat_list = os.path.join(frame_dir, "final_concat.txt")
    with open(final_concat_list, "w") as f:
        f.write(f"file '{os.path.abspath(final_output_with_bgm)}'\n")
        f.write(f"file '{os.path.abspath(final_like_video)}'\n")

    final_output_with_outro = os.path.join(frame_dir, "story_with_bgm_outro.mp4")
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", final_concat_list,
        "-c", "copy",
        final_output_with_outro
    ], check=True)

    print(f"✅ Final story video with fade-out, background music, and outro image created: {final_output_with_outro}")
    return final_output_with_outro


def generate_caption_from_story(title: str) -> str:
     return (
        f"📖 *{title}*\n\n"
        
        '''

🎨✨ Dive into a world where stories come alive through art!
From whimsical children's tales to epic anime adventures, every post is a journey into imagination.
Follow @talesinpix and let your inner child soar! 🚀📖

🔖 #TalesInPix #StoryArt #DigitalStorytelling #VisualNarratives
#KidsStoryTime #ChildrensIllustration #BedtimeTales #InstaKids
#AnimeStories #MangaArt #OtakuLife #AnimeIllustration
#ArtOfTheDay #CreativeJourney #ImaginativeWorlds #DreamscapeArt
#StorybookMagic #AnimeInspiration #WhimsicalArt #NarrativeArt'''
    )

def generate_caption_from_story_carousel(title: str, link: str) -> str:
    return f"""📖 *{title}*

watch in cinematic mode 🎨 {link}

🎨✨ Dive into a world where stories come alive through art!
From whimsical children's tales to epic anime adventures, every post is a journey into imagination.
Follow @talesinpix and let your inner child soar! 🚀📖

🔖 #TalesInPix #StoryArt #DigitalStorytelling #VisualNarratives
#KidsStoryTime #ChildrensIllustration #BedtimeTales #InstaKids
#AnimeStories #MangaArt #OtakuLife #AnimeIllustration
#ArtOfTheDay #CreativeJourney #ImaginativeWorlds #DreamscapeArt
#StorybookMagic #AnimeInspiration #WhimsicalArt #NarrativeArt"""


def generate_tweet_from_story(story_arc: list, youtube_url: str = "", insta_url: str = "") -> (str, str):
    """
    Returns:
    - tweet_caption: A tweet-safe caption that includes the poem, CTA line, and both links, max 280 characters.
    """
    for line in story_arc:
        poem_clean=story_arc("\n", line)

    # Fixed CTA and links (reserve space)
    cta_line = '✨ Experience this story in cinematic art:\n'
    base_links = f"🎬 {youtube_url}\n📸 {insta_url}"
    reserved_length = len(cta_line + base_links)

    # Calculate how many characters are left for the poem
    max_poem_chars = 280 - reserved_length

    # Trim poem if needed
    if len(poem_clean) > max_poem_chars:
        poem_clean = poem_clean[:max_poem_chars - 3].rstrip() + "..."

    tweet_caption = f"{poem_clean}\n{cta_line}{base_links}"
    return tweet_caption

#*****************************INSTAGRAM***Carosel**BEGIN***********************************

def init_carousel_item(media_type: str, media_url: str, is_video: bool = False) -> str:
    endpoint = f"{BASE_URL}/{IG_USER_ID}/media"

    # 🔧 Fix: Use 'image_url' or 'video_url' depending on type
    url_field = "image_url" if media_type.upper() == "IMAGE" else "video_url"

    params = {
        "media_type": media_type.upper(),
        url_field: media_url,
        "is_carousel_item": True,
        "access_token": IG_ACCESS_TOKEN
    }

    resp = requests.post(endpoint, data=params).json()

    if "id" not in resp:
        raise RuntimeError(f"Error initializing carousel item: {resp}")
    
    return resp["id"]


def init_carousel_container(children_ids: list, caption: str) -> str:
    endpoint = f"{BASE_URL}/{IG_USER_ID}/media"
    params = {
        "media_type": "CAROUSEL",
        "children": ",".join(children_ids),
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN
    }
    resp = requests.post(endpoint, data=params).json()
    if "id" not in resp:
        raise RuntimeError(f"Error creating carousel container: {resp}")
    return resp["id"]

def post_carousel(media_items: list, caption: str) -> str:
    children_ids = []
    for item in media_items:
        media_type = item.get('media_type')
        media_url = item.get('media_url')

        print(f"🧾 Uploading item: media_type={media_type}, media_url={media_url}")

        if not media_type or not media_url:
            raise ValueError("Each media item must include 'media_type' and 'media_url'")
        
        container_id = init_carousel_item(media_type, media_url)
        children_ids.append(container_id)

    carousel_id = init_carousel_container(children_ids, caption)
    res = publish_media_container(carousel_id)
    return f"✅ Carousel posted successfully (media ID: {res['id']})"




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
    vertical_shift = output_size[1] // 12  # Slight upward shift (~160px)
    paste_y = max((output_size[1] - image.height) // 2 - vertical_shift, 0)
    #paste_y = (output_size[1] - image.height) // 2
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
        return f"https://twitter.com/user/status/{tweet_id}"
    
    except Exception as e:
        print(f"⚠️ Twitter text post failed: {e}")
        return ""

        return ""
#********************************Twitter End**************************************************************
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


def generate_story_arc(style: str, prompt: str, num_scenes: int = 5) -> list:
    """
    Generate a cinematic visual story arc from a prompt, returning clean scene lines only.
    Removes extra headers, labels, and ignores non-story content.
    """
    if not prompts:
        print(f"⚠️ No prompts found for style: {style}")
        return []

    print(f"chosen prompt: {prompt}")

    instruction = (
        f"Write a cinematic story in exactly {num_scenes} parts for an animated short film. "
        f"Each part should be a short, vivid scene description (under 20 words). "
        f"Structure the arc to include: opener, context, tension/conflict, emotion, climax, and resolution. "
        f"End with a satisfying or reflective final moment. Avoid labels, numbers, or titles. "
        f"Focus on cinematic, emotional, visual storytelling — like Pixar, Ghibli, or DreamWorks."
    )

    msgs = [
        SystemMessage(content="You are a professional animation story writer."),
        HumanMessage(content=f"{prompt}\n\n{instruction}")
    ]

    try:
        response = llm.invoke(msgs).content.strip()
        lines = [line.strip("-•*1234567890. ").strip() for line in response.split("\n") if line.strip()]
        # Remove any lines that are not actual frames
        clean_lines = [
            l for l in lines
            if len(l.split()) > 3
            and not re.match(r'^(part\s*\d+|scene\s*\d+|frame\s*\d+|chapter\s*\d+|title|story)', l.strip(), re.IGNORECASE)
            and not re.match(r'^\s*(hook|conflict|climax|resolution|emotional|rising tension|final thought|context)', l.strip(), re.IGNORECASE)
        ]

        return clean_lines[:num_scenes]
    except Exception as e:
        print(f"⚠️ Story arc generation failed: {e}")
        return []


def generate_consistent_background(story_arc):
    """Generates one vivid, consistent background for the entire story arc."""
    print("\n🧠 Generating consistent scenic base...")
    bg_prompt_msg = [
        SystemMessage(content="You are an AI visual designer."),
        HumanMessage(content=(
            f"Given this story:\n{chr(10).join(story_arc)}\n\n"
            f"Describe one consistent, vivid background setting (natural, urban, sci-fi, etc.) "
            f"where the entire story could take place. Use no more than 20 words."
        ))
    ]
    bg_description = llm.invoke(bg_prompt_msg).content.strip()
    print(f"🪷 Consistent Background: {bg_description}")
    return bg_description

def generate_character_profile(story_arc: list) -> str:
    """
    Generate visually consistent descriptions for both main and significant side characters 
    based on the story arc. This includes physical traits, species (if non-human), clothing, 
    hairstyle, and unique features for animation design. Ensures clear character differentiation.
    """

    prompt = (
        "You are designing characters for an animated film. Based on the following story scenes:\n\n" +
        "\n".join(f"- {scene}" for scene in story_arc) +
        "\n\nDescribe the characters that appear, divided into two sections:\n"
        "**1. Main Character(s):**\n"
        "Describe each main character in under 100 words, including:\n"
        "- Size and shape\n"
        "- Age and gender (if apparent)\n"
        "- Species/type (if non-human)\n"
        "- Clothing/accessories\n"
        "- Hairstyle or surface texture\n"
        "- Color palette\n"
        "- Distinctive visual traits\n\n"
        "**2. Side Character(s):**\n"
        "List any important side characters with brief (1-2 sentence) descriptions of their visual design and relationship to the main character(s).\n\n"
        "Be vivid, concise, and consistent for animation purposes."
    )

    msgs = [
        SystemMessage(content="You are a professional character designer for animated films. Your job is to create clear, vivid, and consistent visual character descriptions."),
        HumanMessage(content=prompt)
    ]

    try:
        response = llm.invoke(msgs).content.strip()
        print(f"🎨 Character profile:\n{response}")
        return response
    except Exception as e:
        print(f"⚠️ Character profile generation failed: {e}")
        return ""



def narrate_scene_with_emotion(scene_description: str, story_arc: list, mode: str = "cinematic") -> str:
    """
    Rewrites a scene into a narrator-style line.
    Modes:
      - "cinematic": emotional and visual, like a Ghibli/Pixar narrator but grounded and simple
      - "viral_simple": optimized for viral Instagram Reels (very obvious, visual, and emotional)
    Ensures key scene elements are preserved.
    """
    full_context = "\n".join(f"{i+1}. {s}" for i, s in enumerate(story_arc))

    important_terms = [
        # Environment & Setting
        "moon", "planet", "forest", "jungle", "tree", "attic", "garden", "cloud",
        "rocket", "city", "village", "portal", "cave", "mountain", "river", "pond",
        "rainbow", "snow globe", "castle", "waterfall", "crater", "sandcastle",

        # Characters & Creatures
        "robot", "astronaut", "wizard", "child", "monkey", "cat", "dog", "dragon",
        "gnome", "bear", "doll", "soldier", "zookeeper", "bunny", "fox", "kitten",
        "hedgehog", "squirrel", "rabbit", "puppy", "mouse", "giraffe", "owl", "turtle",
        "shark", "llama", "dinosaur", "hamster", "whale", "penguin", "elephant",
        "goat", "parrot", "panda", "duckling", "otter",

        # Objects & Props
        "axe", "bulldozer", "crane", "spaceship", "wand", "lantern", "treasure",
        "map", "drawing", "letter", "mirror", "balloon", "star", "hot-air balloon",
        "bubble", "marble", "train", "telescope", "trampoline", "pancake", "slipper",
        "umbrella", "paintbrush", "crayon", "wagon", "fort", "quilt",

        # Actions & Emotions
        "rescue", "battle", "rebellion", "friendship", "hug", "whisper", "cry", "fly",
        "protect", "grow", "save", "build", "charge", "sing", "dance", "juggle",
        "skate", "bake", "paint", "chase", "race", "explore", "discover", "comfort",
        "cheer", "heal", "teach", "guide", "invent",

        # Symbols
        "flower", "leaf", "heart", "fruit", "window", "dream", "sun", "sunset",
        "light", "tear", "hope", "starfish", "comet", "crystal", "stardust"
    ]


    keywords = [kw for kw in important_terms if kw.lower() in scene_description.lower()]
    keyword_hint = f"\nMake sure to include: {', '.join(keywords)}." if keywords else ""

    if mode == "viral_simple":
        prompt = (
            f"You're writing short, emotional captions for Instagram Reels that go viral.\n"
            f"Your job is to turn each scene into a moment that feels real and moving.\n"
            f"The viewer should instantly understand what's happening — and feel something.\n"
            f"Use simple words, clear visuals, and a little more explanation — just enough to spark connection.\n\n"
            f"Here’s the full story for context:\n{full_context}\n\n"
            f"Now rewrite this scene as a short viral caption:\n\n"
            f"Scene: {scene_description}{keyword_hint}\n\n"
            f"- Use 8–16 words.\n"
            f"- Focus on what the viewer sees and feels.\n"
            f"- Include any key object or action (axe, robot, heart, sunset, etc).\n"
            f"- Speak clearly, like you're narrating to a friend.\n"
            f"Return only the final line — no quotes or labels."
        )
        system_msg = "You are a short-form storyteller for viral Instagram Reels. Keep it simple and real."

    else:  # cinematic
        prompt = (
            f"You're a narrator for an animated movie (like Ghibli or Pixar),\nbut the audience is everyday people — no complexity.\n"
            f"Narrate a scene from this story clearly and emotionally.\n"
            f"Here's the full story arc:\n{full_context}\n\n"
            f"Scene to narrate: {scene_description}{keyword_hint}\n\n"
            f"- Use a single short sentence.\n"
            f"- Make it visually rich and emotionally grounded.\n"
            f"- Speak like a calm adult, clearly and simply.\n"
            f"- Avoid abstract or flowery language.\n"
            f"- Return only the final narrator line."
        )
        system_msg = "You are a cinematic narrator who explains magical but grounded moments clearly and warmly."

    msgs = [
        SystemMessage(content=system_msg),
        HumanMessage(content=prompt)
    ]

    try:
        response = llm.invoke(msgs).content.strip()
        return response
    except Exception as e:
        print(f"⚠️ Narration failed: {e}")
        return scene_description


def generate_scenes_from_story(story_arc, bg_description, character_description, mode: str = "cinematic", frame_dir: str = "frames"):

    image_paths = []
    audio_paths = []

    emotional_lines = [narrate_scene_with_emotion(scene, story_arc, mode=mode) for scene in story_arc]
    print(f"🖼️************************ emotional_lines: {emotional_lines}")

    for i, (scene, emotion_line) in enumerate(zip(story_arc, emotional_lines)):
        print(f"\n🎬 Scene {i+1}: {scene}")

        # Generate scenic prompt
        merged_prompt_msg = [
            SystemMessage(content=(
                "You are a prompt engineer for AI image generation. "
                "Combine the background and action into a scenic prompt for visual storytelling. "
                "Keep it cinematic and vertical."
            )),
            HumanMessage(content=(
                f"Use the following background and action to create a detailed, single-scene cinematic prompt for image generation.\n\n"
                f"Background: {bg_description}\n"
                f"Character: {character_description}\n"
                f"Scene Action: {scene}\n\n"
                f"Generate a single vertical cinematic frame in a stylized animation style (Studio Ghibli / Pixar). "
                f"Keep the character visually consistent using the description. No photorealism. No text or labels."
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
                f"Generate a high-resolution animated-style illustration. "
                f"The image should be cinematic, painted or stylized, like from a Pixar, Studio Ghibli, or DreamWorks movie. "
                f"Use soft lighting, expressive composition, and warm color tones. No photorealism. No text or labels."
            )

            # Step 1: Generate base image
            base_image_path = generate_image_from_prompt(animated_prompt)

            # Step 2: Make vertical reel-style image
            reel_frame_path = make_instagram_reel_frame(base_image_path)

            # Step 3: Write emotion line directly to frame path
            final_image_path = os.path.join(frame_dir, f"frame{i:03d}.png")
            write_story_bottom_center(reel_frame_path, poem=emotion_line, output_path=final_image_path)

            image_paths.append(final_image_path)

            # Step 4: Generate voiceover
            audio_path = os.path.join("voiceovers", f"line{i}.mp3")
            synthesize_text(emotion_line, audio_path)
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
        style = random.choice(list(story_styles.keys()))
        print(f"\n story_styles: {style}")
        prompts = story_styles[style]

        prompt = random.choice(prompts)
        story_arc = generate_story_arc(style, prompt, random.randint(5, 10))
        story_title = generate_title_from_story(story_arc)

        print(f"\n story_title: {story_title}")
        print(f"\n story_arc: {story_arc}")

        if not story_arc or len(story_arc) < 3:
            max_retries = 3
            retry_count = 0

            while (not story_arc or len(story_arc) < 3) and retry_count < max_retries:
                print("⚠️ Retrying story arc generation...")
                style = random.choice(list(story_styles.keys()))
                print(f"\n story_styles: {style}")
                prompts = story_styles[style]
                prompt = random.choice(prompts)
                story_arc = generate_story_arc(style, [prompt], random.randint(5, 10))
                story_title = generate_title_from_story(story_arc)
                retry_count += 1

            if not story_arc or len(story_arc) < 3:
                print("❌ Failed to generate a valid story arc after 3 retries.")
                # Optionally raise an error or exit the program here
                # raise Exception("Story arc generation failed.")
            else:
                print("✅ Successfully generated story arc.")
                # Continue with processing story_arc


        print(f"\n story_title: {story_title}")
        print(f"\n story_arc: {story_arc}")

        if not story_arc:
            raise RuntimeError("Story arc generation failed.")

        print("\n📖 Visual Story:")
        for line in story_arc:
            print(" -", line)

        bg_description = generate_consistent_background(story_arc)
        character_description = generate_character_profile(story_arc)

        image_paths, audio_paths = generate_scenes_from_story(
            story_arc, bg_description, character_description, mode=mode, frame_dir=FRAME_DIR
        )
        
        # 0. Make Video
        story_video = combine_images_to_story_video(image_paths, audio_paths,FRAME_DIR, duration_per_image=3)
        print(f"\n✅ Story video created: {story_video}")
        
        '''
        # 1. Generate caption
        caption = generate_caption_from_story(story_title)
        print(f"✅ Caption: {caption}")
        
        # 2. Publish to Youtube
        yt_id = upload_video_to_youtube(video_path=story_video, title=story_title, description=caption, tags=["visual story", "animated tale", "kids", "storytelling", "pixar style", "short film"])
        print(f"✅ YouTube Shorts uploaded: https://youtu.be/{yt_id}")
        
        # 3. Post either Instagram Carousel or Reel (50% chance)
        if random.choice([True, False]):
            print("📸 Mode selected: Instagram Carousel")
            
            # Upload all image paths
            cloudinary_urls = [upload_to_cloudinary(p) for p in image_paths]

            # Remove any broken/missing ones
            cloudinary_urls = [url for url in cloudinary_urls if url]

            if not cloudinary_urls:
                raise RuntimeError("❌ No valid Cloudinary URLs to create carousel.")

            media_items = [{"media_type": "IMAGE", "media_url": url} for url in cloudinary_urls]
            
            print("📦 Final media items to upload:")
            for i, item in enumerate(media_items):
                print(f"Item {i+1}: {item}")
                if not item['media_url']:
                    raise RuntimeError(f"❌ Missing media_url for item {i+1}")

            # Post the carousel
            caption = generate_caption_from_story_carousel(story_title,"https://youtu.be/{yt_id}")
            post_carousel(media_items, caption)
            
        else:
            print("🎬 Mode selected: Instagram Reel")
            post_reel(story_video, caption)
            print("✅ Reel uploaded to Instagram.")
        
        # 5. Publish to Twitter (X)
        yt_url = f"https://youtu.be/{yt_id}" if 'yt_id' in locals() else ""
        insta_url = "https://www.instagram.com/talesinpix/"  # replace with your real profile link
        tweet_caption = generate_tweet_from_story(story_arc, yt_url, insta_url)

        # 3. Post to Twitter (text only)
        tweet_url = post_to_twitter_text_only(tweet_caption)
        print(f"✅ tweet done successfully:{tweet_url}")
        '''
    except Exception as e:
        print(f"⚠️ Failed to generate visual story: {e}")

