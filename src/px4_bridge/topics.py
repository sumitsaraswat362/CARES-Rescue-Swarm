"""PX4 versioned DDS topic names from the installed message definition."""


def topic_name(prefix, direction, name, message_type):
    version = int(getattr(message_type, 'MESSAGE_VERSION', 0))
    suffix = f'_v{version}' if version > 0 else ''
    return f'{prefix.rstrip("/")}/fmu/{direction}/{name}{suffix}'
