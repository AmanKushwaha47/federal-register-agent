import re
from typing import Optional
from .federal_agent import FederalAgent

class RouterAgent:
    """Thin router around FederalAgent to provide alternate command parsing."""
    def __init__(self, agent: Optional[FederalAgent] = None):
        self.agent = agent or FederalAgent()

    async def handle(self, message: str) -> str:
        msg = (message or "").strip()
        if not msg:
            return "Please enter a query. Use `help` for examples."

        lower = msg.lower()
        if lower in ("help", "/help", "commands"):
            meta = await self.agent._get_help_metadata()
            return self.agent._format_help_text(meta)

        if lower.startswith("recent"):
            parts = msg.split()
            if len(parts) == 2 and parts[1].isdigit():
                n = int(parts[1])
                return await self.agent.run("", limit=n)
            return "Usage: recent <number>"

        if lower.startswith("find "):
            agency = msg[5:].strip()
            if not agency:
                return "Usage: find <agency>"
            return await self.agent.run("", filters={"agency": agency})

        if lower.startswith("search "):
            q = msg[7:].strip()
            if not q:
                return "Usage: search <keyword>"
            return await self.agent.run(q)

        # default: search
        return await self.agent.run(msg)