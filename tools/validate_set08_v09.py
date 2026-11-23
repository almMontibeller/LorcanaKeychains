#!/usr/bin/env python3
"""Validate Set 08 v09, including the absence of the unwanted central V."""
import validate_set08_v08 as validation


if __name__ == '__main__':
    validation.build.configure('v09')
    validation.LOGS = validation.build.ROOT/'validation'/validation.build.SET.name/validation.build.VERSION
    validation.main()
