DEFAULT_PROTOCOLS: list[tuple[str, str]] = [
    (
        "Alarm Activation",
        "Activate on-site alarm systems when a threat is confirmed.",
    ),
    (
        "Auto-Lock Doors",
        "Trigger electronic locks to secure entry points.",
    ),
    (
        "Turn on Lights",
        "Switch on selected lights to increase visibility and deterrence.",
    ),
]

SUPPORTED_PROTOCOL_NAMES = {name for name, _ in DEFAULT_PROTOCOLS}
