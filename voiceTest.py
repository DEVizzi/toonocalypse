from google.cloud import texttospeech
import os

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\IzazUlHaque\OneDrive - Black Duck Software\Desktop\MYpROJ\Story_bot\myvoiceoverbot-a0da14b71e20.json"

client = texttospeech.TextToSpeechClient()

voice_names = [
    # US English - expressive and smooth
    
    "en-US-Wavenet-A",   # Male – warm, engaging
    "en-US-Wavenet-C",   # Male – deeper tone #Best
    "en-US-Wavenet-D",   # Male – classic, clear #3
    "en-US-Wavenet-E",   # Male – soft, emotive
    "en-US-Wavenet-F",   # Female – expressive, soothing #2
    "en-US-Wavenet-H",   # Female – artistic, lyrical
    "en-US-Neural2-G",   # Female – very natural, poetic tone
    "en-US-Neural2-J",   # Male – smooth, ideal for slow poetry #1

    # British English – refined and articulate
    "en-GB-Wavenet-B",   # Male – elegant, BBC-style
    "en-GB-Wavenet-D",   # Female – gentle British tone
    "en-GB-Neural2-C",   # Female – very natural and poetic
    "en-GB-Neural2-A",   # Male – rhythmic, ideal for formal verse
    
    
]


synthesis_input = texttospeech.SynthesisInput(text='''Your laughter, a sunbeam, warms my soul,
a hidden truth, a love untold,
My heart beats only for your grace,
a whispered vow, in time and space,
Forever bound, in this embrace.''')

for name in voice_names:
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name=name
    )
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
    
    response = client.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_config
    )

    with open(f"{name}.mp3", "wb") as out:
        out.write(response.audio_content)
        print(f"Saved voice sample: {name}.mp3")
