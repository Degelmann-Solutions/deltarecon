"""JSON documents of the stage contracts: reading, checking, hashing, and writing.

Reading follows the order of ``contracts/v3/README.md``: the JSON profile, the contract
version, and then the schema. Every broken rule raises a :class:`Rejection` that carries
the diagnostic of the contract.

The tool writes contract version 3.1 and reads 1.0, 2.0, 3.0, and 3.1. A document is checked
against the schemas of its own version: a 1.0 document against ``contracts/v1/schemas``, a
2.0 document against ``contracts/v2/schemas``, a 3.0 or 3.1 document against
``contracts/v3/schemas``, which accept both minor versions of 3.

The pack is read from ``contracts/`` at the root of a checkout. A wheel carries a copy of it,
made at build time, as ``degelmann/deltarecon/contracts`` beside this module; an installed
package reads that copy.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

CONTRACT_VERSION = "3.1"
PACKAGED_CONTRACTS = Path(__file__).resolve().parent / "contracts"
CONTRACTS = PACKAGED_CONTRACTS if PACKAGED_CONTRACTS.is_dir() else Path(__file__).resolve().parents[2] / "contracts"
# The versions a reader accepts, each with the schemas of its pack.
SCHEMA_FOLDERS = {"1.0": CONTRACTS / "v1" / "schemas", "2.0": CONTRACTS / "v2" / "schemas",
                  "3.0": CONTRACTS / "v3" / "schemas", "3.1": CONTRACTS / "v3" / "schemas"}
SCHEMA_NAMES = ["common", "run", "changes", "compare", "localise", "run-record"]

RUN_SCHEMA = "run.schema.json"
CHANGES_SCHEMA = "changes.schema.json"
RECORD_SCHEMA = "run-record.schema.json"
RUN_REQUEST = f"{RUN_SCHEMA}#/$defs/run_request"


class Rejection(Exception):
    """A broken rule of the contracts, with the diagnostic it leads to."""

    def __init__(self, code: str, message: str, *, model_point_ids=None, change_ids=None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.model_point_ids = list(model_point_ids or [])
        self.change_ids = list(change_ids or [])

    def diagnostic(self) -> dict:
        entry = {"code": self.code, "message": self.message}
        if self.model_point_ids:
            entry["model_point_ids"] = self.model_point_ids
        if self.change_ids:
            entry["change_ids"] = self.change_ids
        return entry


class DuplicateMember(ValueError):
    """An object repeats a member name."""


# --- JSON profile -------------------------------------------------------------------


def strict_json_text(text: str):
    """Parse under the JSON profile: unique member names and finite binary64 numbers."""
    def unique(pairs):
        names = [name for name, _ in pairs]
        if len(names) != len(set(names)):
            repeated = sorted({name for name in names if names.count(name) > 1})
            raise DuplicateMember(f"duplicate member name {repeated[0]!r}")
        return dict(pairs)

    def reject(literal):
        raise ValueError(f"non-finite literal {literal}")

    def finite_float(literal):
        value = float(literal)
        if value in (float("inf"), float("-inf")):
            raise ValueError(f"number too large for binary64: {literal}")
        return value

    def finite_int(literal):
        value = int(literal)
        try:
            float(value)
        except OverflowError:
            raise ValueError(f"number too large for binary64: {literal[:40]}") from None
        return value

    return json.loads(text, object_pairs_hook=unique, parse_constant=reject,
                      parse_float=finite_float, parse_int=finite_int)


def parse_document(data: bytes) -> dict:
    """Read stored bytes as one document under the JSON profile."""
    if data.startswith(b"\xef\xbb\xbf"):
        raise Rejection("invalid_json", "The text starts with a byte order mark.")
    try:
        value = strict_json_text(data.decode("utf-8"))
    except DuplicateMember as exc:
        raise Rejection("duplicate_member", f"The text is rejected: {exc}.") from None
    except RecursionError:
        raise Rejection("invalid_json", "The text is nested too deeply.") from None
    except ValueError as exc:  # also a JSONDecodeError and a UnicodeDecodeError
        raise Rejection("invalid_json", f"The text is not JSON under the JSON profile: {exc}.") from None
    if not isinstance(value, dict):
        raise Rejection("invalid_json", "The top-level value is not an object.")
    try:  # an escaped lone surrogate parses, but no UTF-8 text can hold it
        json.dumps(value, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError:
        raise Rejection("invalid_json", "A string holds a surrogate code point without its pair.") from None
    return value


def check_version(document: dict) -> None:
    """Reject every contract version but the ones this reader reads, before any schema."""
    version = document.get("contract_version", CONTRACT_VERSION)
    if not isinstance(version, str) or version not in SCHEMA_FOLDERS:
        raise Rejection(
            "unsupported_version",
            f"This reader implements the contract versions {', '.join(SCHEMA_FOLDERS)} only, "
            f"not {json.dumps(document['contract_version'], ensure_ascii=False)[:40]}.")


def document_version(document) -> str:
    """The contract version whose schemas check ``document``: its own when this reader reads it,
    otherwise the version the tool writes."""
    version = document.get("contract_version") if isinstance(document, dict) else None
    return version if isinstance(version, str) and version in SCHEMA_FOLDERS else CONTRACT_VERSION


# --- schemas ------------------------------------------------------------------------


def load_schemas(version: str | None = None) -> dict[str, dict]:
    """The schemas of one contract version, by file name; by default those of the version the tool
    writes."""
    return _schemas(version or CONTRACT_VERSION)


@lru_cache(maxsize=None)
def _schemas(version: str) -> dict[str, dict]:
    folder = SCHEMA_FOLDERS[version]
    return {f"{name}.schema.json": json.loads((folder / f"{name}.schema.json").read_text("utf-8"))
            for name in SCHEMA_NAMES}


def validator(schema: str, version: str | None = None) -> Draft202012Validator:
    """A validator for a schema file, or for one definition ``<file>#/$defs/<name>``, of one
    contract version; by default the version the tool writes. The schema ids are bare file
    names, so each version has a registry of its own."""
    return _validator(schema, version or CONTRACT_VERSION)


@lru_cache(maxsize=None)
def _validator(schema: str, version: str) -> Draft202012Validator:
    schemas = _schemas(version)
    registry = Registry().with_resources(
        (name, Resource.from_contents(content)) for name, content in schemas.items())
    if "#" in schema:
        return Draft202012Validator({"$ref": schema}, registry=registry)
    return Draft202012Validator(schemas[schema], registry=registry)


def schema_errors(document, schema: str) -> list[str]:
    """Schema violations as text, in a stable order, under the schemas of the document's version."""
    errors = sorted(validator(schema, document_version(document)).iter_errors(document),
                    key=lambda e: ([str(p) for p in e.absolute_path], e.message))
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '(document)'}: {e.message}"[:300]
            for e in errors]


def check_schema(document: dict, schema: str, document_type: str | None = None) -> None:
    errors = schema_errors(document, schema)
    if not errors and document_type is not None and document.get("document") != document_type:
        errors = [f"(document): the document type is not {document_type}"]
    if errors:
        raise Rejection("schema_violation", f"The document violates its schema at {errors[0]}")


def read_document(path: Path, schema: str, document_type: str | None = None) -> dict:
    """Read a stored document: JSON profile, contract version, schema."""
    document = parse_document(path.read_bytes())
    check_version(document)
    check_schema(document, schema, document_type)
    return document


# --- artifacts ----------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def artifact_reference(base: Path, path: Path) -> dict:
    """The artifact reference of a stored file, relative to the folder of its document."""
    return {"path": path.relative_to(base).as_posix(), "sha256": sha256_file(path)}


def check_artifact(base: Path, reference: dict) -> Path:
    """The file an artifact reference names, once it exists and has the stated hash."""
    path = base / reference["path"]
    if not path.is_file():
        raise Rejection("artifact_missing", f"The file {reference['path']} does not exist.")
    if sha256_file(path) != reference["sha256"]:
        raise Rejection("artifact_hash_mismatch",
                        f"The file {reference['path']} has another hash than stated.")
    return path


# --- run records --------------------------------------------------------------------


def new_record_id() -> str:
    """The identity of one execution of a procedure: ``record-`` and a random UUID of version 4.

    It is generated anew for every execution and is the only member that names an
    execution; ``run_id`` and ``compare_id`` name the request.
    """
    return f"record-{uuid.uuid4()}"


# --- release identity ---------------------------------------------------------------


def _reference_key(reference: dict) -> str:
    return json.dumps(reference, sort_keys=True, ensure_ascii=False)


def same_release(left: dict, right: dict) -> bool:
    """Equal labels, and references equal as sets (README rule 3)."""
    return (left["label"] == right["label"]
            and {_reference_key(r) for r in left["references"]}
            == {_reference_key(r) for r in right["references"]})


# --- writing ------------------------------------------------------------------------


def document_bytes(document: dict) -> bytes:
    """The stored form: members in the order given, two-space indent, one final line feed."""
    return (json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def write_new(path: Path, data: bytes) -> None:
    """Write a file that must not exist yet. An existing file is never overwritten."""
    with open(path, "xb") as handle:
        handle.write(data)


def check_document(document: dict, schema: str, name: str) -> bytes:
    """The stored form of a document that passes its schema. ``name`` names the file in the error."""
    errors = schema_errors(document, schema)
    if errors:
        raise AssertionError(f"{name} would violate {schema}: {errors[0]}")
    return document_bytes(document)


def write_document(path: Path, document: dict, schema: str) -> None:
    """Write a document after checking that it passes its schema."""
    write_new(path, check_document(document, schema, path.name))


def copy_files(source: Path, target: Path, relatives) -> None:
    """Copy the files ``relatives`` names, relative to ``source``, byte for byte into the same
    layout below ``target``. A name given twice is copied once."""
    for relative in dict.fromkeys(relatives):
        copy = target / relative
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, copy)
