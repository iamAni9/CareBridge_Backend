import os
from dotenv import load_dotenv

load_dotenv()

REQUEST_TYPE_LABELS = {
    "GROCERIES": "grocery shopping",
    "TRANSPORT": "transportation help",
    "MEDICINE": "medicine pickup",
    "FAMILY_CALL": "help making a family call",
    "CAREGIVER": "a caregiver visit",
}


def generate_volunteer_briefing(
    elder_name: str,
    request_type: str,
    distance_km: float,
    elder_note: str | None = None,
    elder_age: int | None = None,
) -> str:
    """
    Generate a warm, informative 2-3 sentence volunteer briefing using Groq LLM.
    Falls back to a static message if Groq fails.
    """
    type_label = REQUEST_TYPE_LABELS.get(request_type, request_type)

    try:
        from groq import Groq

        client = Groq(api_key=os.getenv("GROQ_API_KEY"))

        age_context = f"They are {elder_age} years old. " if elder_age else ""
        note_context = f'They added a note: "{elder_note}". ' if elder_note else ""

        system_prompt = (
            "You are CareBridge, a care coordination assistant. "
            "Your job is to write a short, warm, informative message to a community volunteer "
            "who has been matched to help an elderly person. Be respectful, clear, and encouraging. "
            "Never include distances, addresses, or personal contact info. Plain text only. No bullet points."
        )

        user_prompt = (
            f"{elder_name} needs help with {type_label}. "
            f"{age_context}{note_context}"
            f"Write a briefing for the volunteer. 2-3 sentences max. "
            f"Mention what the task is, any relevant note, and thank them warmly for helping."
        )

        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=120,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()

    except Exception:
        # Fallback — never block request creation because of AI failure
        return f"{elder_name} needs help with {type_label}. Please reach out and assist them."
