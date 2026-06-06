class UnsupportedFileTypeError(ValueError):
    """Raised when the uploaded file type is not supported."""


class FileTooLargeError(ValueError):
    """Raised when the uploaded file exceeds the configured size limit."""


class DocumentProcessingError(Exception):
    """Raised when parsing or chunking a document fails."""


class DocumentNotFoundError(Exception):
    """Raised when a requested document does not exist in the store."""
