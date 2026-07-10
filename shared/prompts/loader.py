"""
loader.py
=========
Loads a role's system prompt from its YAML file and prepends the shared
injection defense block. Every node calls load_prompt(role) instead of
reading YAML files directly or hardcoding prompt text.
"""

import os
import yaml

PROMPT_DIR = os.path.dirname(__file__)

def _load_yaml(filename: str) -> dict:
    path = os.path.join(PROMPT_DIR, filename)

    with open(path, "r") as f:
        return yaml.safe_load(f)

def load_prompt(role: str) -> str:
    """
    Returns the full system prompt for a given role: injection defense
    block + role-specific instructions, in that order.
    """
    defense_block = _load_yaml("_injection_defense_block.yml")["injection_defense_block"]
    role_config = _load_yaml(f"{role}_system.yml")
    return defense_block + "\n" + role_config["prompt"]