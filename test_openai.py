from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("OPENAI_API_KEY")
print("KEY:", key)

client = OpenAI(api_key=key)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Привет"}]
)

print(response.choices[0].message.content)
