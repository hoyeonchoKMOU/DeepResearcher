"""Citation formatting tool for academic papers."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CitationStyle(str, Enum):
    """Supported citation styles."""

    APA = "apa"
    IEEE = "ieee"
    ACM = "acm"
    CHICAGO = "chicago"
    HARVARD = "harvard"
    MLA = "mla"


class CitationInfo(BaseModel):
    """Information needed for citation formatting."""

    authors: list[str] = Field(description="List of author names")
    title: str = Field(description="Paper title")
    year: Optional[int] = Field(default=None, description="Publication year")
    venue: Optional[str] = Field(default=None, description="Journal/Conference name")
    volume: Optional[str] = Field(default=None, description="Volume number")
    issue: Optional[str] = Field(default=None, description="Issue number")
    pages: Optional[str] = Field(default=None, description="Page range")
    doi: Optional[str] = Field(default=None, description="DOI")
    url: Optional[str] = Field(default=None, description="URL")
    publisher: Optional[str] = Field(default=None, description="Publisher name")


class CitationFormatter:
    """Format citations in various academic styles."""

    @staticmethod
    def format_author_apa(author: str) -> str:
        """Format author name for APA style (Last, F. M.)."""
        parts = author.strip().split()
        if len(parts) == 0:
            return ""
        if len(parts) == 1:
            return parts[0]

        last = parts[-1]
        initials = " ".join(f"{p[0]}." for p in parts[:-1] if p)
        return f"{last}, {initials}"

    @staticmethod
    def format_author_ieee(author: str) -> str:
        """Format author name for IEEE style (F. M. Last)."""
        parts = author.strip().split()
        if len(parts) == 0:
            return ""
        if len(parts) == 1:
            return parts[0]

        last = parts[-1]
        initials = " ".join(f"{p[0]}." for p in parts[:-1] if p)
        return f"{initials} {last}"

    @classmethod
    def format_apa(cls, info: CitationInfo) -> str:
        """Format citation in APA 7th edition style.

        Example: Author, A. A., & Author, B. B. (Year). Title. Journal, Volume(Issue), pages. DOI
        """
        parts = []

        # Authors
        if info.authors:
            if len(info.authors) == 1:
                authors_str = cls.format_author_apa(info.authors[0])
            elif len(info.authors) == 2:
                authors_str = f"{cls.format_author_apa(info.authors[0])} & {cls.format_author_apa(info.authors[1])}"
            else:
                # More than 2 authors: First author et al.
                authors_str = f"{cls.format_author_apa(info.authors[0])} et al."
            parts.append(authors_str)

        # Year
        year_str = f"({info.year})" if info.year else "(n.d.)"
        parts.append(year_str)

        # Title (italicized in real formatting)
        parts.append(f"*{info.title}*.")

        # Journal/Venue
        if info.venue:
            venue_str = f"*{info.venue}*"
            if info.volume:
                venue_str += f", {info.volume}"
                if info.issue:
                    venue_str += f"({info.issue})"
            if info.pages:
                venue_str += f", {info.pages}"
            parts.append(venue_str + ".")

        # DOI
        if info.doi:
            parts.append(f"https://doi.org/{info.doi}")
        elif info.url:
            parts.append(info.url)

        return " ".join(parts)

    @classmethod
    def format_ieee(cls, info: CitationInfo, ref_number: int = 1) -> str:
        """Format citation in IEEE style.

        Example: [1] A. A. Author and B. B. Author, "Title," Journal, vol. X, no. Y, pp. Z, Year.
        """
        parts = [f"[{ref_number}]"]

        # Authors
        if info.authors:
            if len(info.authors) <= 3:
                authors_list = [cls.format_author_ieee(a) for a in info.authors]
                if len(authors_list) == 1:
                    authors_str = authors_list[0]
                elif len(authors_list) == 2:
                    authors_str = f"{authors_list[0]} and {authors_list[1]}"
                else:
                    authors_str = f"{', '.join(authors_list[:-1])}, and {authors_list[-1]}"
            else:
                authors_str = f"{cls.format_author_ieee(info.authors[0])} et al."
            parts.append(f"{authors_str},")

        # Title (in quotes)
        parts.append(f'"{info.title},"')

        # Journal/Venue (italicized)
        if info.venue:
            parts.append(f"*{info.venue}*,")

        # Volume, Issue, Pages
        if info.volume:
            parts.append(f"vol. {info.volume},")
        if info.issue:
            parts.append(f"no. {info.issue},")
        if info.pages:
            parts.append(f"pp. {info.pages},")

        # Year
        if info.year:
            parts.append(f"{info.year}.")

        # DOI
        if info.doi:
            parts.append(f"doi: {info.doi}")

        return " ".join(parts)

    @classmethod
    def format_acm(cls, info: CitationInfo) -> str:
        """Format citation in ACM style.

        Example: Author. Year. Title. In Venue. Publisher. DOI
        """
        parts = []

        # Authors
        if info.authors:
            authors_str = ", ".join(info.authors[:3])
            if len(info.authors) > 3:
                authors_str += " et al."
            parts.append(f"{authors_str}.")

        # Year
        parts.append(f"{info.year or 'n.d.'}.")

        # Title
        parts.append(f"{info.title}.")

        # Venue
        if info.venue:
            parts.append(f"In *{info.venue}*.")

        # Publisher
        if info.publisher:
            parts.append(f"{info.publisher}.")

        # DOI
        if info.doi:
            parts.append(f"https://doi.org/{info.doi}")

        return " ".join(parts)

    @classmethod
    def format(cls, info: CitationInfo, style: CitationStyle, **kwargs) -> str:
        """Format citation in specified style.

        Args:
            info: Citation information.
            style: Citation style to use.
            **kwargs: Additional style-specific arguments.

        Returns:
            Formatted citation string.
        """
        formatters = {
            CitationStyle.APA: cls.format_apa,
            CitationStyle.IEEE: cls.format_ieee,
            CitationStyle.ACM: cls.format_acm,
        }

        formatter = formatters.get(style, cls.format_apa)

        if style == CitationStyle.IEEE:
            return formatter(info, kwargs.get("ref_number", 1))

        return formatter(info)

    @classmethod
    def format_bibliography(
        cls,
        citations: list[CitationInfo],
        style: CitationStyle = CitationStyle.APA,
    ) -> str:
        """Format a list of citations as a bibliography.

        Args:
            citations: List of citation information.
            style: Citation style to use.

        Returns:
            Formatted bibliography string.
        """
        lines = ["# References", ""]

        for i, info in enumerate(citations, 1):
            citation = cls.format(info, style, ref_number=i)
            lines.append(citation)
            lines.append("")

        return "\n".join(lines)
