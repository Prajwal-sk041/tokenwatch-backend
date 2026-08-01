from cryptography.fernet import Fernet, InvalidToken

from config import get_settings


def encrypt_api_key(plaintext: str) -> str:
    return Fernet(get_settings().api_key_encryption_key.encode("ascii")).encrypt(
        plaintext.encode("utf-8")
    ).decode("ascii")


def decrypt_api_key(ciphertext: str) -> str:
    try:
        return Fernet(get_settings().api_key_encryption_key.encode("ascii")).decrypt(
            ciphertext.encode("ascii")
        ).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Stored API key cannot be decrypted") from exc


def mask_api_key(plaintext: str) -> str:
    if len(plaintext) <= 8:
        return "••••••••"
    return f"{plaintext[:4]}••••{plaintext[-4:]}"

