"""Entry point for the AI starter kit."""
import os
from src import models


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Please set OPENAI_API_KEY environment variable.")
        return

    client = models.get_openai_client(api_key)
    prompt = "Say hello from AI starter kit."
    response = client.chat.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
    print("AI response:", response.choices[0].message.content)


if __name__ == "__main__":
    main()
