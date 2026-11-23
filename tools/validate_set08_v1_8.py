#!/usr/bin/env python3
"""Validate Set 08 v1.8, including the absence of the unwanted central V."""
import validate_set08_v1_7 as validation


if __name__ == '__main__':
    validation.build.configure('v1.8')
    validation.LOGS = validation.build.ROOT/'validation'/validation.build.SET.name/validation.build.VERSION
    validation.main()
