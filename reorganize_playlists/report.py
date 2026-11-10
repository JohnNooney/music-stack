"""Human-readable run report: ordered sections of lines."""

from __future__ import annotations


class Report:
    def __init__(self) -> None:
        self.sections: dict[str, list[str]] = {}

    def add(self, section: str, line: str) -> None:
        self.sections.setdefault(section, []).append(line)

    def lines(self, section: str) -> list[str]:
        return self.sections.get(section, [])

    def render(self, title: str) -> str:
        out = [title, "=" * len(title)]
        for section, lines in self.sections.items():
            out += ["", f"{section} ({len(lines)})", "-" * (len(section) + len(str(len(lines))) + 3)]
            out += [f"  {line}" for line in lines]
        return "\n".join(out) + "\n"
