#!/usr/bin/env python3

"""Generate Markdown lineup documentation from specification."""

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

logger = logging.getLogger(__name__)


LINEUP_TEMPLATE_NAME = "Lineup.j2"
MAP_TEMPLATE_NAME = "Map.j2"
IMAGE_EXT = ".webp"
IMAGE_SUFFIXES = ("position", "throw")
ALLOWED_STYLES = frozenset({"No-jump", "Jump-throw", "Peak-jump"})


@dataclass(frozen=True)
class LineupSpec:
    """Single lineup entry parsed from the specification file."""

    id: str
    name: str
    style: tuple[str, ...]
    description: str | None = None
    comment: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.style, str):
            object.__setattr__(self, "style", (self.style,))
        else:
            object.__setattr__(self, "style", tuple(self.style))


@dataclass(frozen=True)
class MapSpec:
    """Site section containing an ordered collection of lineups."""

    sites: dict[str, list[LineupSpec]]
    description: str | None = None


@dataclass(frozen=True)
class GenerationConfig:
    """Configuration parameters for a single map generation run."""

    map_name: str
    spec_path: Path
    output_dir: Path
    templates_dir: Path
    images_subdir: str = "images"


def parse_lineup(raw: dict) -> LineupSpec:
    """Validate and construct a LineupSpec from a raw YAML mapping."""

    raw_style = raw["style"]
    styles = (raw_style,) if isinstance(raw_style, str) else tuple(raw_style)

    invalid_styles = set(styles) - ALLOWED_STYLES
    if invalid_styles:
        raise ValueError(
            f"Invalid style(s) {invalid_styles} in lineup '{raw.get('id')}'. "
            f"Allowed: {sorted(ALLOWED_STYLES)}"
        )

    return LineupSpec(
        id=raw["id"],
        name=raw["name"],
        style=styles,
        description=raw.get("description"),
        comment=raw.get("comment"),
    )


def load_spec(path: Path) -> MapSpec:
    """Read and validate the JSON specification from disk."""

    raw_data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw_data, dict) or "sites" not in raw_data:
        raise TypeError(f"Expected a JSON array in {path}")

    sites = {
        site_name: [LineupSpec(**item) for item in lineups]
        for site_name, lineups in raw_data["sites"].items()
    }

    return MapSpec(
        sites=sites,
        description=raw_data.get("description"),
    )


def create_jinja_env(path: Path) -> Environment:
    """Initialize Jinja2 environment for the given templates directory."""

    return Environment(
        loader=FileSystemLoader(path),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def index_existing_images(images_dir: Path) -> set[str]:
    """Return a set of filenames present in the images directory."""

    if not images_dir.is_dir():
        logger.warning("Images directory does not exist: %s", images_dir)
        return set()

    return {entry.name for entry in images_dir.iterdir() if entry.is_file()}


def resolve_lineup_images(
    lineup_id: str,
    available_files: set[str],
    images_subdir: str,
) -> list[str]:
    """Build an ordered list of POSIX image paths for a specific lineup ID."""

    matched: list[str] = []
    for suffix in IMAGE_SUFFIXES:
        filename = f"{lineup_id}_{suffix}{IMAGE_EXT}"
        if filename in available_files:
            matched.append(str(PurePosixPath(images_subdir, filename)))

    if not matched:
        logger.warning("No images found for lineup '%s'", lineup_id)
    return matched


def generate_map_docs(config: GenerationConfig) -> None:
    """Render lineup and map index Markdown files based on the configuration."""

    map_spec = load_spec(config.spec_path)
    env = create_jinja_env(config.templates_dir)
    lineup_template = env.get_template(LINEUP_TEMPLATE_NAME)
    map_template = env.get_template(MAP_TEMPLATE_NAME)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    available_images = index_existing_images(config.output_dir / config.images_subdir)

    sites_index: dict[str, list[dict[str, str]]] = {}

    for site_name, lineups in map_spec.sites.items():
        site_entries: list[dict[str, str]] = []

        for num, lineup in enumerate(lineups, start=1):
            filename = f"{lineup.id}.md"
            images = resolve_lineup_images(
                lineup_id=lineup.id,
                available_files=available_images,
                images_subdir=config.images_subdir,
            )

            rendered_lineup = lineup_template.render(
                map=config.map_name,
                site=site_name,
                num=num,
                name=lineup.name,
                style=lineup.style,
                description=lineup.description,
                comment=lineup.comment,
                images=images,
            )

            (config.output_dir / filename).write_text(rendered_lineup, encoding="utf-8")
            site_entries.append({"name": lineup.name, "filename": filename})

        sites_index[site_name] = site_entries

    rendered_map = map_template.render(
        map=config.map_name,
        description=map_spec.description,
        sites=sites_index,
    )

    index_path = config.output_dir / "README.md"
    index_path.write_text(rendered_map, encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> GenerationConfig:
    """Parse command-line arguments into an immutable configuration object."""

    parser = argparse.ArgumentParser(
        description="Generate Markdown files from a map JSON specification."
    )
    parser.add_argument(
        "--map-name",
        required=True,
        help="Display name of the map (e.g., Haven).",
    )
    parser.add_argument(
        "--spec",
        required=True,
        type=Path,
        dest="spec_path",
        help="Path to the JSON specification file.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Target directory for generated Markdown files.",
    )
    parser.add_argument(
        "--templates-dir",
        required=True,
        type=Path,
        help="Directory containing Jinja2 templates.",
    )
    parser.add_argument(
        "--images-subdir",
        default="images",
        help="Subdirectory inside output-dir containing images (default: images).",
    )

    args = parser.parse_args(argv)
    return GenerationConfig(
        map_name=args.map_name,
        spec_path=args.spec_path,
        output_dir=args.output_dir,
        templates_dir=args.templates_dir,
        images_subdir=args.images_subdir,
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    config = parse_args()

    try:
        generate_map_docs(config)
    except Exception as exc:  # noqa: BLE001
        logger.error("Generation failed: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
