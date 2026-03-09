"""Agent definitions — one class per agent, all inherit BaseAgent."""

from .base import BaseAgent, Task, Result, AgentStatus
from .obchodak import ObchodakAgent
from .textar import TextarAgent
from .postak import PostakAgent
from .strateg import StrategAgent
from .kalendar import KalendarAgent
from .kontrolor import KontrolorAgent
from .archivar import ArchivarAgent
from .udrzbar import UdrzbarAgent
from .hlidac import HlidacAgent
from .planovac import PlanovacAgent
from .spojka import SpojkaAgent
from .vyvojar import VyvojarAgent
from .kouc import KoucAgent

# Registry: name → class
AGENT_CLASSES = {
    "obchodak": ObchodakAgent,
    "textar": TextarAgent,
    "postak": PostakAgent,
    "strateg": StrategAgent,
    "kalendar": KalendarAgent,
    "kontrolor": KontrolorAgent,
    "archivar": ArchivarAgent,
    "udrzbar": UdrzbarAgent,
    "hlidac": HlidacAgent,
    "planovac": PlanovacAgent,
    "spojka": SpojkaAgent,
    "vyvojar": VyvojarAgent,
    "kouc": KoucAgent,
}


def create_all_agents() -> dict[str, BaseAgent]:
    """Instantiate all registered agents."""
    return {name: cls() for name, cls in AGENT_CLASSES.items()}


def get_agent(name: str) -> BaseAgent:
    """Get a single agent instance by name."""
    cls = AGENT_CLASSES.get(name)
    if not cls:
        raise ValueError(f"Unknown agent: {name}. Available: {list(AGENT_CLASSES.keys())}")
    return cls()
