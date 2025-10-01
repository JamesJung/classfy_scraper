"""
HWP5 compatibility wrapper for Python 3
This module provides a compatibility layer to make pyhwp work like hwp5
"""

import sys
import importlib

# Create fake hwp5 module structure
class FakeHwp5Module:
    def __init__(self):
        # Import pyhwp modules
        try:
            import pyhwp
            from pyhwp import hwp5
            
            # Map hwp5 submodules
            self.dataio = type('dataio', (), {
                'ParseError': Exception
            })()
            
            self.errors = type('errors', (), {
                'InvalidHwp5FileError': Exception
            })()
            
            # Try to import HTML transform capabilities
            try:
                from pyhwp.hwp5 import hwp5html
                self.hwp5html = hwp5html
            except:
                # Create a dummy HTMLTransform
                self.hwp5html = type('hwp5html', (), {
                    'HTMLTransform': type('HTMLTransform', (), {})
                })()
            
            # Try to import xmlmodel
            try:
                from pyhwp.hwp5 import xmlmodel
                self.xmlmodel = xmlmodel
            except:
                self.xmlmodel = type('xmlmodel', (), {
                    'Hwp5File': type('Hwp5File', (), {})
                })()
                
        except Exception as e:
            print(f"Warning: Could not properly initialize hwp5 compatibility: {e}")
            # Create minimal stub structure
            self.dataio = type('dataio', (), {
                'ParseError': Exception
            })()
            
            self.errors = type('errors', (), {
                'InvalidHwp5FileError': Exception
            })()
            
            self.hwp5html = type('hwp5html', (), {
                'HTMLTransform': type('HTMLTransform', (), {})
            })()
            
            self.xmlmodel = type('xmlmodel', (), {
                'Hwp5File': type('Hwp5File', (), {})
            })()

# Install the fake module
if 'hwp5' not in sys.modules:
    sys.modules['hwp5'] = FakeHwp5Module()
    sys.modules['hwp5.dataio'] = sys.modules['hwp5'].dataio
    sys.modules['hwp5.errors'] = sys.modules['hwp5'].errors
    sys.modules['hwp5.hwp5html'] = sys.modules['hwp5'].hwp5html
    sys.modules['hwp5.xmlmodel'] = sys.modules['hwp5'].xmlmodel