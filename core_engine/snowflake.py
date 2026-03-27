"""Snowflake algorithm for generating distributed unique IDs."""

import time
import threading
from typing import Tuple


class Snowflake:
    """Distributed unique ID generator using Twitter's Snowflake algorithm.
    
    Structure (64 bits):
    - 1 bit: Sign (always 0)
    - 41 bits: Timestamp in milliseconds (can be used for ~69 years)
    - 10 bits: Machine ID (supports 1024 nodes)
    - 12 bits: Sequence number per millisecond (supports 4096 IDs/ms per node)
    """
    
    # Time epoch: 2026-01-01 00:00:00 UTC
    EPOCH = 1735689600000
    
    SEQUENCE_BITS = 12
    MACHINE_BITS = 10
    
    MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1
    MAX_MACHINE_ID = (1 << MACHINE_BITS) - 1
    
    def __init__(self, machine_id: int = 0) -> None:
        """Initialize snowflake generator.
        
        Args:
            machine_id: Unique machine/node ID (0-1023)
        """
        if not (0 <= machine_id <= self.MAX_MACHINE_ID):
            raise ValueError(f"machine_id must be between 0 and {self.MAX_MACHINE_ID}")
        
        self.machine_id = machine_id
        self.sequence = 0
        self.last_timestamp = -1
        self._lock = threading.Lock()
    
    def _timestamp(self) -> int:
        """Get current timestamp in milliseconds."""
        return int(time.time() * 1000)
    
    def _wait_next_millis(self, last_timestamp: int) -> int:
        """Wait until next millisecond."""
        timestamp = self._timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._timestamp()
        return timestamp
    
    def generate(self) -> int:
        """Generate a unique ID.
        
        Returns:
            64-bit unique integer ID
        """
        with self._lock:
            timestamp = self._timestamp()
            
            if timestamp < self.last_timestamp:
                raise RuntimeError("Clock moved backwards")
            
            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.MAX_SEQUENCE
                if self.sequence == 0:
                    timestamp = self._wait_next_millis(self.last_timestamp)
            else:
                self.sequence = 0
            
            self.last_timestamp = timestamp
            
            # Combine timestamp, machine_id, and sequence into 64-bit ID
            uid = ((timestamp - self.EPOCH) << (self.MACHINE_BITS + self.SEQUENCE_BITS)) | \
                  (self.machine_id << self.SEQUENCE_BITS) | \
                  self.sequence
            
            return uid
    
    def generate_string(self) -> str:
        """Generate a unique ID as string.
        
        Returns:
            Unique ID as string
        """
        return str(self.generate())


# Global snowflake instance
_default_snowflake: Snowflake = None
_init_lock = threading.Lock()


def get_snowflake(machine_id: int = 0) -> Snowflake:
    """Get or create the global snowflake instance.
    
    Args:
        machine_id: Unique machine/node ID (0-1023)
    
    Returns:
        Snowflake instance
    """
    global _default_snowflake
    
    if _default_snowflake is None:
        with _init_lock:
            if _default_snowflake is None:
                _default_snowflake = Snowflake(machine_id)
    
    return _default_snowflake


def generate_user_id() -> str:
    """Generate a unique user ID.
    
    Returns:
        Unique user ID string
    """
    return get_snowflake().generate_string()
