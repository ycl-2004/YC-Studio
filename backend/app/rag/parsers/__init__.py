"""Document parser contracts, built-in implementations, and dispatch."""

from app.rag.parsers.base import BaseParser, ParseResult, ParserRegistrationError
from app.rag.parsers.factory import ParserFactory, UnsupportedFileTypeError, parse_file
from app.rag.parsers.html_parser import HTMLParser
from app.rag.parsers.markdown_parser import MarkdownParser
from app.rag.parsers.pdf_parser import NoTextLayerError, PDFParser
from app.rag.parsers.txt_parser import TextDecodingError, TextParser
from app.rag.parsers.word_parser import WordParser

__all__ = [
    "BaseParser",
    "HTMLParser",
    "MarkdownParser",
    "NoTextLayerError",
    "PDFParser",
    "ParseResult",
    "ParserFactory",
    "ParserRegistrationError",
    "TextDecodingError",
    "TextParser",
    "UnsupportedFileTypeError",
    "WordParser",
    "parse_file",
]
