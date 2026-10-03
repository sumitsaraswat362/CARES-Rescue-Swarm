import enum
from dataclasses import dataclass

class MessageType(enum.Enum):
    HEARTBEAT = 1
    TELEMETRY = 2
    TASK_BID = 3
    CONSENSUS = 4
    SURVEY_DATA = 5
    EMERGENCY = 6
    ACK = 7

@dataclass
class Message:
    msg_type: MessageType
    sender_id: int
    receiver_id: int  # -1 for broadcast, -2 for GCS
    payload: dict
    timestamp: float
    ttl: int = 3  # max hops
    msg_id: int = 0  # unique ID

