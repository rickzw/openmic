"""Personal dictionary management.

Stores custom words, names, and jargon that get passed to the LLM
for better recognition and spelling.
"""

from openmic.config import Config


class PersonalDictionary:
    """Manages a list of custom terms stored in the app config."""

    def __init__(self, config: Config):
        self.config = config

    def get_entries(self):
        """Returns list of {"term": "...", "definition": "..."}."""
        return self.config.get("personal_dictionary", [])

    def add_entry(self, term: str, definition: str = ""):
        """Add or update a dictionary entry."""
        entries = self.get_entries()
        for e in entries:
            if e["term"].lower() == term.lower():
                e["definition"] = definition
                self.config.set("personal_dictionary", entries)
                return
        entries.append({"term": term, "definition": definition})
        self.config.set("personal_dictionary", entries)

    def remove_entry(self, term: str):
        """Remove a dictionary entry by term name."""
        entries = [e for e in self.get_entries() if e["term"].lower() != term.lower()]
        self.config.set("personal_dictionary", entries)

    def get_prompt_hint(self) -> str:
        """Build a prompt hint string for the Whisper API.

        Returns a comma-separated list of terms that helps Whisper
        recognize custom vocabulary.
        """
        entries = self.get_entries()
        if not entries:
            return ""
        return ", ".join(e["term"] for e in entries)

    def get_llm_context(self) -> str:
        """Build context string for the LLM polish step.

        Returns a formatted block that gets appended to the LLM system prompt.
        """
        entries = self.get_entries()
        if not entries:
            return ""
        lines = []
        for e in entries:
            if e.get("definition"):
                lines.append("- %s: %s" % (e["term"], e["definition"]))
            else:
                lines.append("- %s" % e["term"])
        return (
            "\n\nPersonal dictionary (these terms may appear in the text, "
            "use the correct spelling shown here):\n"
            + "\n".join(lines)
        )
