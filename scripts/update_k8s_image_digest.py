#!/usr/bin/env python3
"""
Kubernetes Image Digest Updater for Cerberus Release Workflows.
Safely updates an application image digest in a Kustomization file while ensuring:
1. The digest is never identical to any Dockerfile base image.
2. The digest strictly matches sha256:[a-f0-9]{64}.
3. The repository name conforms to Cerberus standards.
"""

import argparse
import re
import sys
from pathlib import Path

import yaml

from scripts.validate_k8s_image_pinning import get_dockerfile_base_digests

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def update_image_digest(
    kustomization_path: Path,
    image_name: str,
    new_digest: str,
    dockerfile_path: Path = PROJECT_ROOT / "Dockerfile",
) -> int:
    """Update image digest in kustomization YAML."""
    clean_digest = new_digest.strip().lower()
    if not clean_digest.startswith("sha256:"):
        clean_digest = f"sha256:{clean_digest}"

    if not re.match(r"^sha256:[a-f0-9]{64}$", clean_digest):
        print(f"Error: '{new_digest}' is not a valid 64-character sha256 hex digest.", file=sys.stderr)
        return 1

    base_digests = get_dockerfile_base_digests(dockerfile_path)
    if clean_digest in [d.lower() for d in base_digests]:
        print(
            f"Error: Digest '{clean_digest}' matches Dockerfile base image. "
            f"Refusing to set application image digest equal to base OS image.",
            file=sys.stderr,
        )
        return 1

    if not kustomization_path.exists():
        print(f"Error: Kustomization file not found: {kustomization_path}", file=sys.stderr)
        return 1

    content = yaml.safe_load(kustomization_path.read_text(encoding="utf-8"))
    images = content.get("images", [])

    updated = False
    for img in images:
        if img.get("name") == image_name:
            img["digest"] = clean_digest
            img.pop("newTag", None)
            updated = True
            break

    if not updated:
        images.append(
            {
                "name": image_name,
                "newName": "ghcr.io/cerberus-ai/cerberus-ai",
                "digest": clean_digest,
            }
        )
        content["images"] = images

    kustomization_path.write_text(yaml.dump(content, sort_keys=False), encoding="utf-8")
    print(f"Successfully updated image '{image_name}' to digest '{clean_digest}' in {kustomization_path.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Update Kubernetes application image digest")
    parser.add_argument("--kustomization", "-k", default="k8s/kustomization.yaml", help="Path to kustomization.yaml")
    parser.add_argument("--image", "-i", default="cerberus-ai", help="Image name to update")
    parser.add_argument("--digest", "-d", required=True, help="New image sha256 digest")
    args = parser.parse_args()

    k_path = Path(args.kustomization).resolve()
    return update_image_digest(k_path, args.image, args.digest)


if __name__ == "__main__":
    sys.exit(main())
