import re
import random
import string

def slugify(text: str) -> str:
    """Lowercase, strip non-alphanumeric (keep hyphens/spaces), collapse to kebab-case."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    return text.strip("-")

def make_property_slug(address_string: str) -> str:
    """Generate slug for a property based on its address string."""
    return slugify(address_string)

def make_zone_slug(name: str, state: str, zone_type: str) -> str:
    """Generate slug for a spatial zone."""
    base_name = name
    if zone_type == "SCHOOL_CATCHMENT":
        # Strip common trailing suffixes
        suffixes = [" catchment area", " catchment", " zone", " zones"]
        lower_name = base_name.lower()
        for suffix in suffixes:
            if lower_name.endswith(suffix):
                base_name = base_name[: -len(suffix)].strip()
                break
    
    return slugify(base_name)

def ensure_unique_slug(base: str, seen: set[str]) -> str:
    """Append random 4-char alphanumeric suffix on collision."""
    if base not in seen:
        seen.add(base)
        return base
    for _ in range(10):
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        candidate = f"{base}-{suffix}"
        if candidate not in seen:
            seen.add(candidate)
            return candidate
    raise RuntimeError(f"Could not generate unique slug after 10 attempts for: {base}")
