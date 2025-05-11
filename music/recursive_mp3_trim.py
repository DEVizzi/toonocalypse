
import os
import subprocess

# ✅ Path to ffmpeg executable
#FFMPEG_PATH = r"C:\ffmpeg\bin\ffmpeg.exe"  # Update this path if needed

def trim_mp3_file(input_file):
    folder, name = os.path.split(input_file)
    name_no_ext = os.path.splitext(name)[0]
    temp_name = f"{name_no_ext}_tmp.mp3"
    temp_path = os.path.join(folder, temp_name)

    try:
        # Run ffmpeg: extract first 30 seconds without re-encoding
        result = subprocess.run([
            FFMPEG_PATH,
            "-y",                   # Overwrite output if exists
            "-i", input_file,
            "-ss", "0",
            "-t", "30",
            "-c", "copy",
            temp_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode == 0 and os.path.exists(temp_path):
            os.remove(input_file)
            os.rename(temp_path, input_file)
            print(f"✅ Trimmed and replaced: {input_file}")
        else:
            print(f"❌ Failed: {input_file}\n{result.stderr.decode().strip()}")
    except Exception as e:
        print(f"⚠️ Error processing {input_file}: {e}")

def process_all_mp3s(root_dir):
    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.lower().endswith(".mp3"):
                full_path = os.path.join(root, file)
                trim_mp3_file(full_path)

if __name__ == "__main__":
    base_dir = os.path.abspath(".")
    print(f"🔍 Searching for MP3s in: {base_dir}")
    process_all_mp3s(base_dir)
    print("🎉 All done!")
