import bcrypt


def hash_password(password):
    return bcrypt.hashpw(bytes(password, encoding='utf-8'), bcrypt.gensalt(rounds=12))


def verify_password(password,hashed):
    return bcrypt.checkpw(bytes(password, encoding='utf-8'), bytes(hashed))