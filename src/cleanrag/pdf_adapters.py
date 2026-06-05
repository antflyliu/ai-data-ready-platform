from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from .models import DocumentIR, Element, Page, ParseWarning, Source


PdfKind = Literal["digital", "scanned", "mixed", "unknown"]
AdapterStatus = Literal["success", "skipped", "failed"]


@dataclass(frozen=True)
class PdfProfile:
    kind: PdfKind
    page_count: int
    text_pages: int
    image_pages: int
    image_count: int
    encrypted: bool = False
    page_dimensions: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def image_only(self) -> bool:
        return self.kind == "scanned"


@dataclass
class AdapterResult:
    adapter_name: str
    role: str
    status: AdapterStatus
    reason: str = ""
    document: DocumentIR | None = None
    warnings: list[ParseWarning] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "adapter_name": self.adapter_name,
            "role": self.role,
            "status": self.status,
            "reason": self.reason,
            "warning_count": len(self.warnings)
            + (len(self.document.parse_warnings) if self.document else 0),
            "element_count": len(self.document.elements) if self.document else 0,
            "table_count": len(self.document.tables) if self.document else 0,
            "image_count": len(self.document.images) if self.document else 0,
            "metadata": self.metadata,
        }


class PdfAdapter(Protocol):
    name: str
    role: str

    def availability(self) -> dict[str, Any]:
        ...

    def supports(self, profile: PdfProfile) -> bool:
        ...

    def parse(self, path: Path, dataset_id: str, document_id: str, source: Source, profile: PdfProfile) -> AdapterResult:
        ...


def parse_pdf(path: Path, dataset_id: str, document_id: str, source: Source) -> DocumentIR:
    profile = inspect_pdf_profile(path)
    adapters = default_pdf_adapters()
    selected = select_pdf_workflow(profile, adapters)
    registry = [_adapter_registry_entry(adapter) for adapter in adapters]
    results: list[AdapterResult] = []
    winner: DocumentIR | None = None
    run_all = _run_all_available_adapters()

    for adapter in selected:
        result = _run_adapter(adapter, path, dataset_id, document_id, source, profile)
        results.append(result)
        if result.status == "success" and result.document and result.document.elements and winner is None:
            winner = result.document
            if not run_all:
                break

    if winner is None and profile.image_only and not _force_image_pdf_parsing():
        winner = _image_only_document(dataset_id, document_id, source, profile, results)
    elif winner is None:
        winner = _failed_pdf_document(dataset_id, document_id, source, profile, results)

    _attach_workflow_metadata(winner, profile, results, registry, selected)
    return winner


def inspect_pdf_profile(path: Path) -> PdfProfile:
    try:
        import fitz  # type: ignore[import-not-found]
    except Exception as exc:
        return PdfProfile(
            kind="unknown",
            page_count=0,
            text_pages=0,
            image_pages=0,
            image_count=0,
            warnings=[f"PyMuPDF preflight is unavailable: {exc}"],
        )

    try:
        pdf = fitz.open(path)
    except Exception as exc:
        return PdfProfile(
            kind="unknown",
            page_count=0,
            text_pages=0,
            image_pages=0,
            image_count=0,
            warnings=[f"PDF preflight failed: {exc}"],
        )

    page_dimensions: list[dict[str, Any]] = []
    text_pages = 0
    image_pages = 0
    image_count = 0
    try:
        encrypted = bool(getattr(pdf, "is_encrypted", False))
        for page_index, page in enumerate(pdf, start=1):
            rect = page.rect
            page_dimensions.append(
                {
                    "page_number": page_index,
                    "width": float(rect.width),
                    "height": float(rect.height),
                    "unit": "pt",
                }
            )
            if page.get_text("text").strip():
                text_pages += 1
            page_images = len(page.get_images(full=True))
            if page_images:
                image_pages += 1
                image_count += page_images
    finally:
        pdf.close()

    page_count = len(page_dimensions)
    if page_count and text_pages == 0 and image_pages >= page_count:
        kind: PdfKind = "scanned"
    elif page_count and text_pages and image_pages:
        kind = "mixed"
    elif page_count and text_pages:
        kind = "digital"
    else:
        kind = "unknown"

    return PdfProfile(
        kind=kind,
        page_count=page_count,
        text_pages=text_pages,
        image_pages=image_pages,
        image_count=image_count,
        encrypted=encrypted,
        page_dimensions=page_dimensions,
    )


def default_pdf_adapters() -> list[PdfAdapter]:
    return [
        MinerUAdapter(),
        OpenDataLoaderAdapter(),
        DoclingAdapter(),
        UnstructuredAdapter(),
        PyMuPDFAdapter(),
        DeepDocAdapter(),
        DeepdoctectionAdapter(),
        PaddleOCRAdapter(),
        TextractAdapter(),
    ]


def select_pdf_workflow(profile: PdfProfile, adapters: list[PdfAdapter]) -> list[PdfAdapter]:
    by_name = {adapter.name: adapter for adapter in adapters}
    if profile.kind == "scanned":
        names = [
            "paddleocr",
            "textract",
            "mineru",
            "docling",
            "opendataloader",
            "deepdoc",
            "deepdoctection",
            "pymupdf",
        ]
    elif profile.kind == "mixed":
        names = [
            "opendataloader",
            "docling",
            "unstructured",
            "mineru",
            "deepdoc",
            "deepdoctection",
            "pymupdf",
            "paddleocr",
            "textract",
        ]
    else:
        names = [
            "opendataloader",
            "mineru",
            "docling",
            "unstructured",
            "deepdoc",
            "deepdoctection",
            "pymupdf",
        ]
    return [by_name[name] for name in names if name in by_name]


class OpenDataLoaderAdapter:
    name = "opendataloader"
    role = "digital-primary"

    def availability(self) -> dict[str, Any]:
        module = _module_availability("opendataloader_pdf")
        java = _java_runtime_availability()
        return {
            "available": bool(module.get("available") and java.get("available")),
            "module": module,
            "java": java,
            "reason": "OpenDataLoader module and Java 11+ runtime are available"
            if module.get("available") and java.get("available")
            else "; ".join(
                item
                for item in [
                    str(module.get("reason") or "") if not module.get("available") else "",
                    str(java.get("reason") or "") if not java.get("available") else "",
                ]
                if item
            ),
        }

    def supports(self, profile: PdfProfile) -> bool:
        if profile.kind == "scanned":
            return _force_image_pdf_parsing() or bool(os.environ.get("CLEANRAG_OPENDATALOADER_HYBRID"))
        return True

    def parse(self, path: Path, dataset_id: str, document_id: str, source: Source, profile: PdfProfile) -> AdapterResult:
        try:
            import opendataloader_pdf  # type: ignore[import-not-found]
        except Exception as exc:
            return AdapterResult(self.name, self.role, "skipped", f"opendataloader_pdf unavailable: {exc}")

        try:
            with tempfile.TemporaryDirectory(prefix="cleanrag-opendataloader-") as temp:
                output_dir = Path(temp)
                hybrid = os.environ.get("CLEANRAG_OPENDATALOADER_HYBRID") or None
                hybrid_mode = os.environ.get("CLEANRAG_OPENDATALOADER_HYBRID_MODE") or None
                with _configured_java_home():
                    opendataloader_pdf.convert(
                        input_path=str(path),
                        output_dir=str(output_dir),
                        format="json,markdown",
                        quiet=True,
                        hybrid=hybrid,
                        hybrid_mode=hybrid_mode,
                    )
                json_path = _first_output(output_dir, "*.json")
                markdown_path = _first_output(output_dir, "*.md") or _first_output(output_dir, "*.markdown")
                if json_path is None:
                    warning = ParseWarning(
                        warning_id=f"{document_id}_warn_opendataloader_no_json",
                        severity="high",
                        scope="document",
                        message="OpenDataLoader conversion completed but no JSON output was found.",
                        source_parser=self.name,
                    )
                    return AdapterResult(self.name, self.role, "failed", warning.message, warnings=[warning])
                payload = json.loads(json_path.read_text(encoding="utf-8"))
                markdown = markdown_path.read_text(encoding="utf-8") if markdown_path else ""
                document = _document_from_opendataloader_payload(
                    payload,
                    markdown,
                    dataset_id,
                    document_id,
                    source,
                )
                return AdapterResult(self.name, self.role, "success", document=document)
        except Exception as exc:
            warning = ParseWarning(
                warning_id=f"{document_id}_warn_opendataloader_failed",
                severity="medium",
                scope="document",
                message=f"OpenDataLoader conversion failed: {exc}",
                source_parser=self.name,
            )
            return AdapterResult(self.name, self.role, "failed", warning.message, warnings=[warning])


class PyMuPDFAdapter:
    name = "pymupdf"
    role = "fallback"

    def availability(self) -> dict[str, Any]:
        return _module_availability("fitz")

    def supports(self, profile: PdfProfile) -> bool:
        return True

    def parse(self, path: Path, dataset_id: str, document_id: str, source: Source, profile: PdfProfile) -> AdapterResult:
        try:
            import fitz  # type: ignore[import-not-found]
        except Exception as exc:
            return AdapterResult(self.name, self.role, "skipped", f"PyMuPDF unavailable: {exc}")

        pages: list[Page] = []
        elements: list[Element] = []
        warnings: list[ParseWarning] = []
        image_count = 0
        try:
            pdf = fitz.open(path)
            for page_index, page in enumerate(pdf, start=1):
                rect = page.rect
                image_count += len(page.get_images(full=True))
                pages.append(
                    Page(
                        page_id=f"{document_id}_page_{page_index:04d}",
                        page_number=page_index,
                        width=float(rect.width),
                        height=float(rect.height),
                        unit="pt",
                    )
                )
                for block in page.get_text("blocks"):
                    x0, y0, x1, y1, text, *_ = block
                    content = " ".join(str(text).split())
                    if not content:
                        continue
                    elements.append(
                        Element(
                            element_id=f"{document_id}_el_{len(elements) + 1:04d}",
                            type=_noise_hint_type(content, "paragraph"),
                            text=content,
                            markdown=content,
                            page_number=page_index,
                            bbox=[float(x0), float(y0), float(x1), float(y1)],
                            confidence=0.85,
                            source_parser=self.name,
                        )
                    )
            pdf.close()
        except Exception as exc:
            warning = ParseWarning(
                warning_id=f"{document_id}_warn_pymupdf_failed",
                severity="high",
                scope="document",
                message=f"PDF parsing failed: {exc}",
                source_parser=self.name,
            )
            return AdapterResult(self.name, self.role, "failed", warning.message, warnings=[warning])

        if not elements and pages and image_count >= len(pages):
            warnings.append(
                ParseWarning(
                    warning_id=f"{document_id}_warn_image_only_pdf",
                    severity="high",
                    scope="document",
                    message="Image-only or scanned PDF detected. OCR/hybrid parsing is required.",
                    source_parser=self.name,
                )
            )
        elif not elements:
            warnings.append(
                ParseWarning(
                    warning_id=f"{document_id}_warn_no_text",
                    severity="medium",
                    scope="document",
                    message="PDF parser produced no text elements.",
                    source_parser=self.name,
                )
            )

        document = DocumentIR(
            "0.1",
            document_id,
            dataset_id,
            source,
            pages=pages,
            elements=elements,
            parse_warnings=warnings,
            metadata={
                "parser_status": "parsed",
                "parser": self.name,
                "fallback_parser": True,
                "image_count": image_count,
                "image_only": bool(pages and not elements and image_count >= len(pages)),
            },
        )
        return AdapterResult(self.name, self.role, "success", document=document)


class DoclingAdapter:
    name = "docling"
    role = "digital-primary"

    def availability(self) -> dict[str, Any]:
        return _module_availability("docling.document_converter")

    def supports(self, profile: PdfProfile) -> bool:
        return True

    def parse(self, path: Path, dataset_id: str, document_id: str, source: Source, profile: PdfProfile) -> AdapterResult:
        try:
            from docling.document_converter import DocumentConverter  # type: ignore[import-not-found]
        except Exception as exc:
            return AdapterResult(self.name, self.role, "skipped", f"Docling unavailable: {exc}")

        try:
            result = DocumentConverter().convert(str(path))
            markdown = result.document.export_to_markdown()
            document = _document_from_plaintext(markdown, dataset_id, document_id, source, self.name, profile, markdown=True)
            return AdapterResult(self.name, self.role, "success", document=document)
        except Exception as exc:
            warning = ParseWarning(
                warning_id=f"{document_id}_warn_docling_failed",
                severity="medium",
                scope="document",
                message=f"Docling conversion failed: {exc}",
                source_parser=self.name,
            )
            return AdapterResult(self.name, self.role, "failed", warning.message, warnings=[warning])


class UnstructuredAdapter:
    name = "unstructured"
    role = "digital-primary"

    def availability(self) -> dict[str, Any]:
        return _module_availability("unstructured.partition.pdf")

    def supports(self, profile: PdfProfile) -> bool:
        return True

    def parse(self, path: Path, dataset_id: str, document_id: str, source: Source, profile: PdfProfile) -> AdapterResult:
        try:
            from unstructured.partition.pdf import partition_pdf  # type: ignore[import-not-found]
        except Exception as exc:
            return AdapterResult(self.name, self.role, "skipped", f"Unstructured unavailable: {exc}")

        try:
            raw_elements = partition_pdf(filename=str(path))
        except Exception as exc:
            warning = ParseWarning(
                warning_id=f"{document_id}_warn_unstructured_failed",
                severity="medium",
                scope="document",
                message=f"Unstructured PDF partition failed: {exc}",
                source_parser=self.name,
            )
            return AdapterResult(self.name, self.role, "failed", warning.message, warnings=[warning])

        elements: list[Element] = []
        title_stack: list[str] = []
        for raw in raw_elements:
            text = str(raw).strip()
            if not text:
                continue
            category = str(getattr(raw, "category", "") or raw.__class__.__name__).lower()
            element_type = _map_category(category)
            if element_type == "title":
                title_stack = [text]
            metadata = getattr(raw, "metadata", None)
            page_number = getattr(metadata, "page_number", None)
            elements.append(
                Element(
                    element_id=f"{document_id}_el_{len(elements) + 1:04d}",
                    type=_noise_hint_type(text, element_type),
                    text=text,
                    markdown=text,
                    page_number=_as_int(page_number),
                    title_path=list(title_stack),
                    confidence=0.85,
                    source_parser=self.name,
                    metadata={"unstructured_category": category},
                )
            )

        warnings: list[ParseWarning] = []
        if not elements and profile.page_count:
            warnings.append(
                ParseWarning(
                    warning_id=f"{document_id}_warn_unstructured_no_text",
                    severity="medium",
                    scope="document",
                    message="Unstructured returned no text elements.",
                    source_parser=self.name,
                )
            )
        document = DocumentIR(
            "0.1",
            document_id,
            dataset_id,
            source,
            pages=_pages_from_profile(document_id, profile),
            elements=elements,
            parse_warnings=warnings,
            metadata={"parser_status": "parsed", "parser": self.name, "image_only": profile.image_only},
        )
        return AdapterResult(self.name, self.role, "success", document=document)


class TextractAdapter:
    name = "textract"
    role = "ocr"

    def availability(self) -> dict[str, Any]:
        return _module_availability("textract")

    def supports(self, profile: PdfProfile) -> bool:
        return profile.kind in {"scanned", "mixed", "unknown"}

    def parse(self, path: Path, dataset_id: str, document_id: str, source: Source, profile: PdfProfile) -> AdapterResult:
        try:
            import textract  # type: ignore[import-not-found]
        except Exception as exc:
            return AdapterResult(self.name, self.role, "skipped", f"Textract unavailable: {exc}")

        try:
            raw = textract.process(str(path))
            text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            document = _document_from_plaintext(text, dataset_id, document_id, source, self.name, profile)
            return AdapterResult(self.name, self.role, "success", document=document)
        except Exception as exc:
            warning = ParseWarning(
                warning_id=f"{document_id}_warn_textract_failed",
                severity="high",
                scope="document",
                message=f"Textract OCR/extraction failed: {exc}",
                source_parser=self.name,
            )
            return AdapterResult(self.name, self.role, "failed", warning.message, warnings=[warning])


class ConfiguredCommandAdapter:
    role = "external"
    env_var = ""
    module_names: tuple[str, ...] = ()
    command_names: tuple[str, ...] = ()
    supported_kinds: tuple[PdfKind, ...] = ("digital", "scanned", "mixed", "unknown")

    def availability(self) -> dict[str, Any]:
        configured = bool(os.environ.get(self.env_var))
        detected_modules = [name for name in self.module_names if _has_module_spec(name)]
        detected_commands = [name for name in self.command_names if _which(name)]
        return {
            "available": configured,
            "configured": configured,
            "env_var": self.env_var,
            "detected_modules": detected_modules,
            "detected_commands": detected_commands,
            "reason": "configured command bridge is available"
            if configured
            else f"set {self.env_var} to a JSON command array with {{input}} and {{output}} placeholders",
        }

    def supports(self, profile: PdfProfile) -> bool:
        return profile.kind in self.supported_kinds

    def parse(self, path: Path, dataset_id: str, document_id: str, source: Source, profile: PdfProfile) -> AdapterResult:
        command_value = os.environ.get(self.env_var)
        if not command_value:
            return AdapterResult(self.name, self.role, "skipped", self.availability()["reason"])
        try:
            command_template = json.loads(command_value)
            if not isinstance(command_template, list) or not all(isinstance(item, str) for item in command_template):
                raise ValueError("command must be a JSON array of strings")
        except Exception as exc:
            warning = ParseWarning(
                warning_id=f"{document_id}_warn_{self.name}_command_invalid",
                severity="high",
                scope="document",
                message=f"{self.name} command configuration is invalid: {exc}",
                source_parser=self.name,
            )
            return AdapterResult(self.name, self.role, "failed", warning.message, warnings=[warning])

        timeout_seconds = int(os.environ.get("CLEANRAG_ADAPTER_COMMAND_TIMEOUT", "300"))
        try:
            with tempfile.TemporaryDirectory(prefix=f"cleanrag-{self.name}-") as temp:
                output_dir = Path(temp)
                command = [
                    item.format(input=str(path), output=str(output_dir), filename=path.name)
                    for item in command_template
                ]
                try:
                    completed = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        timeout=timeout_seconds,
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    message = f"{self.name} command timed out after {timeout_seconds} seconds"
                    if exc.stderr:
                        message = f"{message}: {exc.stderr}"
                    recovered = _recover_partial_adapter_output(
                        self.name,
                        self.role,
                        output_dir,
                        dataset_id,
                        document_id,
                        source,
                        profile,
                        message,
                    )
                    if recovered:
                        return recovered
                    raise RuntimeError(message) from exc
                if completed.returncode != 0:
                    message = (completed.stderr or completed.stdout or "").strip() or f"exit {completed.returncode}"
                    recovered = _recover_partial_adapter_output(
                        self.name,
                        self.role,
                        output_dir,
                        dataset_id,
                        document_id,
                        source,
                        profile,
                        message,
                    )
                    if recovered:
                        return recovered
                    raise RuntimeError(message)
                document = _document_from_adapter_output(output_dir, dataset_id, document_id, source, self.name, profile)
                return AdapterResult(self.name, self.role, "success", document=document)
        except Exception as exc:
            warning = ParseWarning(
                warning_id=f"{document_id}_warn_{self.name}_failed",
                severity="high" if self.role == "ocr" else "medium",
                scope="document",
                message=f"{self.name} command adapter failed: {exc}",
                source_parser=self.name,
            )
            return AdapterResult(self.name, self.role, "failed", warning.message, warnings=[warning])


class MinerUAdapter(ConfiguredCommandAdapter):
    name = "mineru"
    role = "digital-primary"
    env_var = "CLEANRAG_MINERU_COMMAND"
    module_names = ("mineru",)
    command_names = ("mineru",)


class DeepDocAdapter(ConfiguredCommandAdapter):
    name = "deepdoc"
    role = "vision-layout"
    env_var = "CLEANRAG_DEEPDOC_COMMAND"
    module_names = ("deepdoc",)
    command_names = ("deepdoc",)


class DeepdoctectionAdapter(ConfiguredCommandAdapter):
    name = "deepdoctection"
    role = "vision-layout"
    env_var = "CLEANRAG_DEEPDOCTECTION_COMMAND"
    module_names = ("deepdoctection",)
    command_names = ("deepdoctection",)


class PaddleOCRAdapter(ConfiguredCommandAdapter):
    name = "paddleocr"
    role = "ocr"
    env_var = "CLEANRAG_PADDLEOCR_COMMAND"
    module_names = ("paddleocr",)
    command_names = ("paddleocr",)
    supported_kinds = ("scanned", "mixed", "unknown")

    def availability(self) -> dict[str, Any]:
        configured = super().availability()
        if configured.get("available"):
            return configured
        if os.environ.get("CLEANRAG_DISABLE_PADDLEOCR_AUTO", "").lower() in {"1", "true", "yes"}:
            return {
                **configured,
                "available": False,
                "configured": False,
                "reason": "PaddleOCR auto bridge disabled by CLEANRAG_DISABLE_PADDLEOCR_AUTO",
            }
        script = _repo_root() / "scripts" / "paddleocr_pdf_bridge.py"
        dependencies_available = _has_module_spec("paddleocr") and _has_module_spec("fitz")
        if dependencies_available and script.exists():
            return {
                **configured,
                "available": True,
                "configured": False,
                "bridge_script": str(script),
                "reason": "PaddleOCR and PyMuPDF are installed; built-in bridge will be used",
            }
        return {
            **configured,
            "available": False,
            "bridge_script": str(script),
            "reason": "install optional OCR dependencies or set CLEANRAG_PADDLEOCR_COMMAND",
        }

    def parse(self, path: Path, dataset_id: str, document_id: str, source: Source, profile: PdfProfile) -> AdapterResult:
        if os.environ.get(self.env_var):
            return super().parse(path, dataset_id, document_id, source, profile)
        availability = self.availability()
        if not availability.get("available"):
            return AdapterResult(self.name, self.role, "skipped", str(availability.get("reason") or "PaddleOCR unavailable"))
        script = Path(str(availability.get("bridge_script")))
        window_size = os.environ.get("CLEANRAG_PADDLEOCR_WINDOW_SIZE")
        if window_size:
            windowed_script = _repo_root() / "scripts" / "paddleocr_windowed_pdf_bridge.py"
            if not windowed_script.exists():
                return AdapterResult(
                    self.name,
                    self.role,
                    "skipped",
                    f"PaddleOCR windowed bridge script is missing: {windowed_script}",
                )
            script = windowed_script
        command_parts = [
            sys.executable,
            str(script),
            "--input",
            "{input}",
            "--output",
            "{output}",
            "--lang",
            os.environ.get("CLEANRAG_PADDLEOCR_LANG", "ch"),
            "--dpi",
            os.environ.get("CLEANRAG_PADDLEOCR_DPI", "30"),
            "--text-det-limit-side-len",
            os.environ.get("CLEANRAG_PADDLEOCR_TEXT_DET_LIMIT_SIDE_LEN", "320"),
            "--model-source",
            os.environ.get("CLEANRAG_PADDLEOCR_MODEL_SOURCE", "aistudio"),
        ]
        if window_size:
            command_parts.extend(["--window-size", window_size])
        max_pages = os.environ.get("CLEANRAG_PADDLEOCR_MAX_PAGES")
        if max_pages:
            command_parts.extend(["--max-pages", max_pages])
        start_page = os.environ.get("CLEANRAG_PADDLEOCR_START_PAGE")
        if start_page:
            command_parts.extend(["--start-page", start_page])
        end_page = os.environ.get("CLEANRAG_PADDLEOCR_END_PAGE")
        if end_page:
            command_parts.extend(["--end-page", end_page])
        checkpoint_every = os.environ.get("CLEANRAG_PADDLEOCR_CHECKPOINT_EVERY")
        if checkpoint_every:
            command_parts.extend(["--checkpoint-every", checkpoint_every])
        min_confidence = os.environ.get("CLEANRAG_PADDLEOCR_MIN_CONFIDENCE")
        if min_confidence:
            command_parts.extend(["--min-confidence", min_confidence])
        max_windows = os.environ.get("CLEANRAG_PADDLEOCR_MAX_WINDOWS")
        if max_windows and window_size:
            command_parts.extend(["--max-windows", max_windows])
        window_cache_dir = os.environ.get("CLEANRAG_PADDLEOCR_WINDOW_CACHE_DIR")
        if window_cache_dir and window_size:
            command_parts.extend(["--work-dir", window_cache_dir])
        reuse_existing = os.environ.get("CLEANRAG_PADDLEOCR_REUSE_EXISTING_WINDOWS")
        if reuse_existing and window_size:
            flag = "--reuse-existing" if reuse_existing.lower() in {"1", "true", "yes"} else "--no-reuse-existing"
            command_parts.append(flag)
        command = json.dumps(command_parts)
        old_command = os.environ.get(self.env_var)
        os.environ[self.env_var] = command
        try:
            return super().parse(path, dataset_id, document_id, source, profile)
        finally:
            if old_command is None:
                os.environ.pop(self.env_var, None)
            else:
                os.environ[self.env_var] = old_command


def _recover_partial_adapter_output(
    adapter_name: str,
    role: str,
    output_dir: Path,
    dataset_id: str,
    document_id: str,
    source: Source,
    profile: PdfProfile,
    failure_message: str,
) -> AdapterResult | None:
    try:
        document = _document_from_adapter_output(output_dir, dataset_id, document_id, source, adapter_name, profile)
    except Exception:
        return None
    if not document.elements:
        return None

    warning = ParseWarning(
        warning_id=f"{document_id}_warn_{adapter_name}_partial_recovery",
        severity="high" if role == "ocr" else "medium",
        scope="document",
        message=f"{adapter_name} command failed, but partial output was recovered: {failure_message}",
        source_parser=adapter_name,
    )
    document.parse_warnings.insert(0, warning)
    document.metadata["partial_output"] = True
    document.metadata["adapter_command_failed"] = True
    document.metadata["adapter_command_error"] = failure_message
    return AdapterResult(
        adapter_name=adapter_name,
        role=role,
        status="success",
        reason="adapter command failed but partial output was recovered",
        document=document,
        metadata={"partial_recovery": True, "command_error": failure_message},
    )


def _run_adapter(
    adapter: PdfAdapter,
    path: Path,
    dataset_id: str,
    document_id: str,
    source: Source,
    profile: PdfProfile,
) -> AdapterResult:
    availability = adapter.availability()
    if not adapter.supports(profile):
        return AdapterResult(
            adapter.name,
            adapter.role,
            "skipped",
            f"adapter does not support {profile.kind} PDFs in the current configuration",
            metadata={"availability": availability},
        )
    if not availability.get("available"):
        return AdapterResult(
            adapter.name,
            adapter.role,
            "skipped",
            str(availability.get("reason") or "adapter dependency is unavailable"),
            metadata={"availability": availability},
        )
    result = adapter.parse(path, dataset_id, document_id, source, profile)
    result.metadata.setdefault("availability", availability)
    return result


def _attach_workflow_metadata(
    document: DocumentIR,
    profile: PdfProfile,
    results: list[AdapterResult],
    registry: list[dict[str, Any]],
    selected: list[PdfAdapter],
) -> None:
    selected_names = [adapter.name for adapter in selected]
    result_metadata = [result.to_metadata() for result in results]
    workflow = {
        "profile": _profile_metadata(profile),
        "selected_adapters": selected_names,
        "adapter_results": result_metadata,
        "registered_adapters": registry,
        "run_all_available_adapters": _run_all_available_adapters(),
    }
    document.metadata["pdf_workflow"] = workflow
    document.metadata["pdf_profile"] = _profile_metadata(profile)
    document.metadata["source_image_only"] = profile.image_only
    document.metadata["image_only"] = bool((document.metadata.get("image_only") or profile.image_only) and not document.elements)
    document.metadata["ocr_required"] = bool(document.metadata.get("ocr_required") or (profile.image_only and not document.elements))


def _profile_metadata(profile: PdfProfile) -> dict[str, Any]:
    dimensions_sample = profile.page_dimensions[:5]
    return {
        "kind": profile.kind,
        "page_count": profile.page_count,
        "text_pages": profile.text_pages,
        "image_pages": profile.image_pages,
        "image_count": profile.image_count,
        "encrypted": profile.encrypted,
        "page_dimensions_sample": dimensions_sample,
        "page_dimensions_omitted": max(0, len(profile.page_dimensions) - len(dimensions_sample)),
        "warnings": profile.warnings,
    }


def _image_only_document(
    dataset_id: str,
    document_id: str,
    source: Source,
    profile: PdfProfile,
    results: list[AdapterResult],
) -> DocumentIR:
    unavailable = [result.adapter_name for result in results if result.status == "skipped" and result.role == "ocr"]
    failed = [result.adapter_name for result in results if result.status == "failed" and result.role == "ocr"]
    warnings: list[ParseWarning] = []
    for result in results:
        if result.role == "ocr" and result.status == "failed":
            warnings.extend(result.warnings)
            if result.document:
                warnings.extend(result.document.parse_warnings)
    warning_parts = [
        "Image-only or scanned PDF detected by preflight. OCR/hybrid parsing is required.",
    ]
    if unavailable:
        warning_parts.append(f"Skipped OCR adapters: {', '.join(unavailable)}.")
    if failed:
        warning_parts.append(f"Failed OCR adapters: {', '.join(failed)}.")
    warnings.append(
        ParseWarning(
            warning_id=f"{document_id}_warn_image_only_pdf",
            severity="high",
            scope="document",
            message=" ".join(warning_parts),
            source_parser="pdf_workflow",
        )
    )
    return DocumentIR(
        "0.1",
        document_id,
        dataset_id,
        source,
        pages=_pages_from_profile(document_id, profile),
        elements=[],
        parse_warnings=warnings,
        metadata={
            "parser_status": "skipped",
            "parser": "pdf_workflow",
            "image_count": profile.image_count,
            "text_pages": profile.text_pages,
            "image_only": True,
            "ocr_required": True,
        },
    )


def _failed_pdf_document(
    dataset_id: str,
    document_id: str,
    source: Source,
    profile: PdfProfile,
    results: list[AdapterResult],
) -> DocumentIR:
    warnings: list[ParseWarning] = []
    for result in results:
        warnings.extend(result.warnings)
        if result.document:
            warnings.extend(result.document.parse_warnings)
    if not warnings:
        warnings.append(
            ParseWarning(
                warning_id=f"{document_id}_warn_no_pdf_adapter",
                severity="high",
                scope="document",
                message="No PDF adapter produced parseable text.",
                source_parser="pdf_workflow",
            )
        )
    return DocumentIR(
        "0.1",
        document_id,
        dataset_id,
        source,
        pages=_pages_from_profile(document_id, profile),
        elements=[],
        parse_warnings=warnings,
        metadata={
            "parser_status": "failed",
            "parser": "pdf_workflow",
            "image_only": profile.image_only,
            "ocr_required": profile.image_only,
        },
    )


def _adapter_registry_entry(adapter: PdfAdapter) -> dict[str, Any]:
    availability = adapter.availability()
    return {
        "name": adapter.name,
        "role": adapter.role,
        "available": bool(availability.get("available")),
        "availability": availability,
    }


def _document_from_opendataloader_payload(
    payload: dict[str, Any],
    markdown: str,
    dataset_id: str,
    document_id: str,
    source: Source,
) -> DocumentIR:
    pages = [
        Page(page_id=f"{document_id}_page_{page_number:04d}", page_number=page_number)
        for page_number in range(1, int(payload.get("number of pages") or 0) + 1)
    ]
    elements: list[Element] = []
    tables: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    title_stack: list[str] = []
    _flatten_opendataloader_nodes(
        payload.get("kids", []),
        document_id,
        elements,
        tables,
        images,
        title_stack,
        inherited_type=None,
    )
    warnings: list[ParseWarning] = []
    if not elements and pages:
        warnings.append(
            ParseWarning(
                warning_id=f"{document_id}_warn_opendataloader_no_text",
                severity="high",
                scope="document",
                message="OpenDataLoader produced no text elements. If this is a scanned PDF, run hybrid OCR.",
                source_parser="opendataloader",
            )
        )
    return DocumentIR(
        "0.1",
        document_id,
        dataset_id,
        source,
        pages=pages,
        elements=elements,
        tables=tables,
        images=images,
        parse_warnings=warnings,
        metadata={
            "parser_status": "parsed",
            "parser": "opendataloader",
            "markdown_output_chars": len(markdown),
            "source_title": payload.get("title"),
            "source_author": payload.get("author"),
        },
    )


def _flatten_opendataloader_nodes(
    nodes: Any,
    document_id: str,
    elements: list[Element],
    tables: list[dict[str, Any]],
    images: list[dict[str, Any]],
    title_stack: list[str],
    inherited_type: str | None,
) -> None:
    if not isinstance(nodes, list):
        return
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type") or inherited_type or "unknown").strip().lower()
        effective_type = _map_opendataloader_type(node_type, inherited_type)
        content = _node_text(node)
        if effective_type == "table":
            tables.append(node)
            content = content or _table_text(node)
        if effective_type == "image":
            images.append(node)

        if content:
            if effective_type == "title":
                level = int(node.get("heading level") or 1)
                title_stack[:] = title_stack[: max(level - 1, 0)] + [content]
            elements.append(
                Element(
                    element_id=f"{document_id}_el_{len(elements) + 1:04d}",
                    type=effective_type,
                    text=content,
                    markdown=content,
                    page_number=_as_int(node.get("page number")),
                    bbox=_bbox(node.get("bounding box")),
                    title_path=list(title_stack),
                    confidence=0.95,
                    source_parser="opendataloader",
                    metadata={
                        "opendataloader_type": node_type,
                        "opendataloader_id": node.get("id"),
                    },
                )
            )

        child_inherited_type = effective_type if effective_type in {"header", "footer"} else inherited_type
        for key in ("kids", "list items"):
            _flatten_opendataloader_nodes(
                node.get(key),
                document_id,
                elements,
                tables,
                images,
                title_stack,
                child_inherited_type,
            )
        for row in node.get("rows", []) if isinstance(node.get("rows"), list) else []:
            for cell in row.get("cells", []) if isinstance(row, dict) else []:
                _flatten_opendataloader_nodes(
                    cell.get("kids"),
                    document_id,
                    elements,
                    tables,
                    images,
                    title_stack,
                    child_inherited_type,
                )


def _document_from_plaintext(
    text: str,
    dataset_id: str,
    document_id: str,
    source: Source,
    parser_name: str,
    profile: PdfProfile,
    markdown: bool = False,
) -> DocumentIR:
    title_stack: list[str] = []
    elements: list[Element] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        element_type = "paragraph"
        content = line
        if markdown and line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            content = line[level:].strip()
            title_stack = title_stack[: max(level - 1, 0)] + [content]
            element_type = "title"
        elements.append(
            Element(
                element_id=f"{document_id}_el_{len(elements) + 1:04d}",
                type=_noise_hint_type(content, element_type),
                text=content,
                markdown=raw_line if markdown else content,
                title_path=list(title_stack),
                confidence=0.75,
                source_parser=parser_name,
                metadata={"line_number": line_number},
            )
        )
    warnings: list[ParseWarning] = []
    if not elements and profile.page_count:
        warnings.append(
            ParseWarning(
                warning_id=f"{document_id}_warn_{parser_name}_no_text",
                severity="high" if profile.image_only else "medium",
                scope="document",
                message=f"{parser_name} produced no text elements.",
                source_parser=parser_name,
            )
        )
    return DocumentIR(
        "0.1",
        document_id,
        dataset_id,
        source,
        pages=_pages_from_profile(document_id, profile),
        elements=elements,
        parse_warnings=warnings,
        metadata={"parser_status": "parsed", "parser": parser_name, "image_only": profile.image_only},
    )


def _document_from_adapter_output(
    output_dir: Path,
    dataset_id: str,
    document_id: str,
    source: Source,
    parser_name: str,
    profile: PdfProfile,
) -> DocumentIR:
    json_path = _first_output(output_dir, "*.json")
    markdown_path = _first_output(output_dir, "*.md") or _first_output(output_dir, "*.markdown")
    text_path = _first_output(output_dir, "*.txt")
    if json_path is not None:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "kids" in payload:
            return _document_from_opendataloader_payload(payload, "", dataset_id, document_id, source)
        if isinstance(payload, dict):
            return _document_from_cleanrag_adapter_payload(payload, dataset_id, document_id, source, parser_name, profile)
    if markdown_path is not None:
        return _document_from_plaintext(
            markdown_path.read_text(encoding="utf-8"),
            dataset_id,
            document_id,
            source,
            parser_name,
            profile,
            markdown=True,
        )
    if text_path is not None:
        return _document_from_plaintext(
            text_path.read_text(encoding="utf-8"),
            dataset_id,
            document_id,
            source,
            parser_name,
            profile,
        )
    raise RuntimeError("adapter command completed but produced no supported JSON/Markdown/text output")


def _document_from_cleanrag_adapter_payload(
    payload: dict[str, Any],
    dataset_id: str,
    document_id: str,
    source: Source,
    parser_name: str,
    profile: PdfProfile,
) -> DocumentIR:
    pages = _pages_from_adapter_payload(document_id, payload, profile)
    elements: list[Element] = []
    for index, raw_element in enumerate(_as_list(payload.get("elements")), start=1):
        if not isinstance(raw_element, dict):
            continue
        text = _normalized_text(raw_element.get("text"))
        if not text:
            continue
        raw_metadata = raw_element.get("metadata")
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        external_id = raw_element.get("element_id") or raw_element.get("id")
        if external_id is not None:
            metadata = {**metadata, "external_element_id": str(external_id)}
        source_parser = str(raw_element.get("source_parser") or payload.get("adapter") or parser_name)
        elements.append(
            Element(
                element_id=f"{document_id}_el_{index:04d}",
                type=str(raw_element.get("type") or "paragraph"),
                text=text,
                markdown=_normalized_text(raw_element.get("markdown")) or text,
                page_number=_as_int(raw_element.get("page_number")),
                bbox=_bbox(raw_element.get("bbox")),
                title_path=[
                    str(item)
                    for item in raw_element.get("title_path", [])
                    if isinstance(raw_element.get("title_path"), list) and item is not None
                ],
                confidence=_as_float(raw_element.get("confidence"), default=0.75),
                source_parser=source_parser,
                metadata=metadata,
            )
        )

    tables = [item for item in _as_list(payload.get("tables")) if isinstance(item, dict)]
    images = [item for item in _as_list(payload.get("images")) if isinstance(item, dict)]
    warnings = _warnings_from_adapter_payload(payload, document_id, parser_name, profile, bool(elements))
    payload_metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    adapter_name = str(payload.get("adapter") or parser_name)
    return DocumentIR(
        "0.1",
        document_id,
        dataset_id,
        source,
        pages=pages,
        elements=elements,
        tables=tables,
        images=images,
        parse_warnings=warnings,
        metadata={
            "parser_status": "parsed",
            "parser": adapter_name,
            "adapter_output_schema": payload.get("schema_version") or payload.get("schema"),
            **payload_metadata,
            "source_image_only": profile.image_only,
            "image_only": bool((payload_metadata.get("image_only") or profile.image_only) and not elements),
            "ocr_required": bool(payload_metadata.get("ocr_required") or (profile.image_only and not elements)),
        },
    )


def _pages_from_adapter_payload(document_id: str, payload: dict[str, Any], profile: PdfProfile) -> list[Page]:
    raw_pages = [item for item in _as_list(payload.get("pages")) if isinstance(item, dict)]
    if not raw_pages:
        return _pages_from_profile(document_id, profile)
    pages: list[Page] = []
    for index, raw_page in enumerate(raw_pages, start=1):
        page_number = _as_int(raw_page.get("page_number")) or index
        pages.append(
            Page(
                page_id=f"{document_id}_page_{page_number:04d}",
                page_number=page_number,
                width=_as_float(raw_page.get("width")),
                height=_as_float(raw_page.get("height")),
                unit=str(raw_page.get("unit") or "pt"),
            )
        )
    return pages


def _warnings_from_adapter_payload(
    payload: dict[str, Any],
    document_id: str,
    parser_name: str,
    profile: PdfProfile,
    has_elements: bool,
) -> list[ParseWarning]:
    warnings: list[ParseWarning] = []
    for index, raw_warning in enumerate(_as_list(payload.get("warnings")), start=1):
        if isinstance(raw_warning, str):
            warnings.append(
                ParseWarning(
                    warning_id=f"{document_id}_warn_{parser_name}_{index:04d}",
                    severity="medium",
                    scope="document",
                    message=raw_warning,
                    source_parser=parser_name,
                )
            )
        elif isinstance(raw_warning, dict):
            warnings.append(
                ParseWarning(
                    warning_id=str(raw_warning.get("warning_id") or f"{document_id}_warn_{parser_name}_{index:04d}"),
                    severity=str(raw_warning.get("severity") or "medium"),
                    scope=str(raw_warning.get("scope") or "document"),
                    message=str(raw_warning.get("message") or "Adapter emitted an unspecified warning."),
                    page_number=_as_int(raw_warning.get("page_number")),
                    source_parser=str(raw_warning.get("source_parser") or parser_name),
                )
            )
    if not has_elements and profile.page_count:
        warnings.append(
            ParseWarning(
                warning_id=f"{document_id}_warn_{parser_name}_no_text",
                severity="high" if profile.image_only else "medium",
                scope="document",
                message=f"{parser_name} adapter output contained no text elements.",
                source_parser=parser_name,
            )
        )
    return warnings


def _map_opendataloader_type(node_type: str, inherited_type: str | None) -> str:
    if inherited_type in {"header", "footer"}:
        return inherited_type
    if node_type in {"heading", "title"}:
        return "title"
    if node_type in {"paragraph", "caption", "list item", "text block"}:
        return "paragraph"
    if node_type in {"table"}:
        return "table"
    if node_type in {"picture", "image", "figure"}:
        return "image"
    if node_type in {"header", "footer"}:
        return node_type
    if node_type in {"list"}:
        return "list"
    return "unknown"


def _map_category(category: str) -> str:
    lowered = category.lower()
    if "title" in lowered:
        return "title"
    if "table" in lowered:
        return "table"
    if "list" in lowered:
        return "list"
    if "image" in lowered or "figure" in lowered:
        return "image"
    return "paragraph"


def _node_text(node: dict[str, Any]) -> str:
    for key in ("content", "text", "description"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    return ""


def _normalized_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _table_text(node: dict[str, Any]) -> str:
    rows = []
    for row in node.get("rows", []) if isinstance(node.get("rows"), list) else []:
        cells = []
        for cell in row.get("cells", []) if isinstance(row, dict) else []:
            cell_text_parts: list[str] = []
            _collect_text(cell.get("kids"), cell_text_parts)
            cells.append(" ".join(cell_text_parts).strip())
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _collect_text(nodes: Any, parts: list[str]) -> None:
    if not isinstance(nodes, list):
        return
    for node in nodes:
        if isinstance(node, dict):
            text = _node_text(node)
            if text:
                parts.append(text)
            _collect_text(node.get("kids"), parts)


def _pages_from_profile(document_id: str, profile: PdfProfile) -> list[Page]:
    return [
        Page(
            page_id=f"{document_id}_page_{int(item['page_number']):04d}",
            page_number=int(item["page_number"]),
            width=float(item["width"]) if item.get("width") is not None else None,
            height=float(item["height"]) if item.get("height") is not None else None,
            unit=str(item.get("unit") or "unknown"),
        )
        for item in profile.page_dimensions
        if item.get("page_number") is not None
    ]


def _module_availability(module_name: str) -> dict[str, Any]:
    module = sys.modules.get(module_name)
    if module is not None:
        return {
            "available": True,
            "module": module_name,
            "reason": "module is already loaded",
        }
    try:
        available = importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        available = False
    return {
        "available": available,
        "module": module_name,
        "reason": "module import spec found" if available else f"module {module_name} is not installed",
    }


def _java_runtime_availability() -> dict[str, Any]:
    if os.environ.get("CLEANRAG_OPENDATALOADER_SKIP_JAVA_CHECK", "").lower() in {"1", "true", "yes"}:
        return {"available": True, "reason": "Java check skipped by environment"}

    java_home = os.environ.get("CLEANRAG_JAVA_HOME") or os.environ.get("JAVA_HOME")
    java_path = str(Path(java_home) / "bin" / "java.exe") if java_home and os.name == "nt" else None
    if java_path is None and java_home:
        java_path = str(Path(java_home) / "bin" / "java")
    command = java_path or "java"
    try:
        completed = subprocess.run(
            [command, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as exc:
        return {"available": False, "command": command, "reason": f"Java runtime check failed: {exc}"}
    output = f"{completed.stdout}\n{completed.stderr}".strip()
    major = _parse_java_major_version(output)
    available = completed.returncode == 0 and major is not None and major >= 11
    return {
        "available": available,
        "command": command,
        "major_version": major,
        "reason": f"Java major version {major} detected" if available else "Java 11+ runtime is required",
    }


def _parse_java_major_version(output: str) -> int | None:
    marker = 'version "'
    if marker not in output:
        return None
    raw = output.split(marker, 1)[1].split('"', 1)[0]
    first = raw.split(".", 1)[0]
    if first == "1":
        parts = raw.split(".")
        if len(parts) > 1:
            first = parts[1]
    try:
        return int(first)
    except ValueError:
        return None


def _has_module_spec(module_name: str) -> bool:
    if module_name in sys.modules:
        return True
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _which(command_name: str) -> str | None:
    from shutil import which

    return which(command_name)


def _first_output(output_dir: Path, pattern: str) -> Path | None:
    matches = sorted(output_dir.glob(pattern))
    if matches:
        return matches[0]
    matches = sorted(output_dir.rglob(pattern))
    return matches[0] if matches else None


@contextmanager
def _configured_java_home():
    java_home = os.environ.get("CLEANRAG_JAVA_HOME")
    if not java_home:
        yield
        return

    old_java_home = os.environ.get("JAVA_HOME")
    old_path = os.environ.get("PATH", "")
    java_bin = str(Path(java_home) / "bin")
    os.environ["JAVA_HOME"] = java_home
    os.environ["PATH"] = f"{java_bin}{os.pathsep}{old_path}"
    try:
        yield
    finally:
        if old_java_home is None:
            os.environ.pop("JAVA_HOME", None)
        else:
            os.environ["JAVA_HOME"] = old_java_home
        os.environ["PATH"] = old_path


def _run_all_available_adapters() -> bool:
    return os.environ.get("CLEANRAG_PDF_RUN_ALL_AVAILABLE", "").lower() in {"1", "true", "yes"}


def _force_image_pdf_parsing() -> bool:
    return os.environ.get("CLEANRAG_FORCE_IMAGE_PDF_PARSING", "").lower() in {"1", "true", "yes"}


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bbox(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _noise_hint_type(text: str, default_type: str) -> str:
    lowered = text.strip().lower()
    if lowered.startswith("header:"):
        return "header"
    if lowered.startswith("footer:"):
        return "footer"
    if lowered.startswith("watermark:"):
        return "watermark"
    return default_type
