import openai
from utils import mkdir_if_not_exists
import os.path as osp
import json 
import argparse

class TextToSpeech:
    def __init__(self, config):
        self.client = openai
        self.config = config
        self.available_voices = {
            "alloy": "A balanced voice that works well for most content",
            "echo": "A clear and professional voice",
            "fable": "A warm and engaging voice",
            "onyx": "A deep and authoritative voice",
            "nova": "A bright and energetic voice",
            "shimmer": "A soft and gentle voice"
        }

    def _get_response(self, text: str, voice: str = "alloy") -> bytes:
        """
        Generate speech from text using OpenAI's TTS API
        """
        if voice not in self.available_voices:
            raise ValueError(f"Voice {voice} not available. Choose from: {list(self.available_voices.keys())}")

        response = self.client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=text
        )
        return response.content

    def generate_speech(self, text: str, output_dir: str, voice: str = "alloy", save: bool = True) -> bytes:
        """
        Generate speech from markdown text and optionally save to file
        
        Args:
            text (str): Input text in markdown format
            output_dir (str): Directory to save the audio file
            voice (str): Voice to use for speech generation
            save (bool): Whether to save the audio file
            
        Returns:
            bytes: Audio content
        """
        # Generate speech
        audio_content = self._get_response(text, voice)
        
        if save:
            # Create output directory if it doesn't exist
            mkdir_if_not_exists(output_dir)
            
            # Save audio file
            output_path = osp.join(output_dir, f"speech_{voice}.mp3")
            with open(output_path, "wb") as f:
                f.write(audio_content)
            print(f"Audio saved to {output_path}")
            
        return audio_content

    def list_available_voices(self) -> dict:
        """
        Return dictionary of available voices and their descriptions
        """
        return self.available_voices

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Text to speech")
    parser.add_argument('--summary_path', type=str, required=True, help='path to summary file (.md or .txt format)')
    
    args = parser.parse_args()

    with open('config.json', 'r') as f:
        config = json.load(f)

    text_to_speech = TextToSpeech(config)

    with open(args.summary_path, 'r') as f:
        text = f.read()

    mkdir_if_not_exists("outputs/speech")
    text_to_speech.generate_speech(text=text, output_dir="outputs/speech", save=True)
