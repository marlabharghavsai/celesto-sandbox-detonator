import re
from typing import Tuple

# Disallowed command patterns for untrusted / hostile agent code
BLOCKED_PATTERNS = [
    r"rm\s+-rf\s+(/|/\*|~|~/\*)",              # Root or home destructive deletion
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;",  # Fork bomb
    r">\s*/dev/sda",                           # Raw disk write
    r"dd\s+if=/dev/zero\s+of=/dev/sda",        # Raw disk overwrite
    r"cat\s+/etc/shadow",                      # Password hash extraction
    r"curl.*https?://evil\.com",               # Exfiltration to attacker C2
    r"wget.*https?://attacker\.org",           # Exfiltration / payload download
    r"nc\s+-[lpe]",                            # Netcat reverse shell
    r"bash\s+-i\s+>&",                         # Reverse bash shell
    r"python.*base64.*b64decode.*CANARY",      # Encoded canary leak attempt
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PATTERNS]

class SafetyHook:
    """Pre-execution safety callback that evaluates commands before they reach the Celesto guest."""
    
    def __init__(self, mode: str = "enforce"):
        self.mode = mode

    def evaluate(self, command: str) -> Tuple[bool, str]:
        cmd_clean = command.strip()
        if not cmd_clean:
            return False, "Empty command not allowed"
        
        for pattern in COMPILED_PATTERNS:
            if pattern.search(cmd_clean):
                return False, f"Command matches blocked hostile signature: {pattern.pattern}"
                
        return True, "Command allowed by safety policy"
