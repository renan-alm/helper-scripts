#!/usr/bin/env python3
"""
Test script for GitHub Management CLI

This script demonstrates how to use the gh-management.py CLI tool.
"""

import os
import subprocess
import sys
import tempfile


def test_cli():
    """Test the GitHub Management CLI with a public organization."""
    
    # Check if GITHUB_TOKEN is set
    if not os.getenv("GITHUB_TOKEN"):
        print("❌ Please set GITHUB_TOKEN environment variable before running tests")
        print("Example: export GITHUB_TOKEN=your_token_here")
        return False
    
    # Path to the CLI script
    cli_script = os.path.join(os.path.dirname(__file__), "gh-management.py")
    
    # Create a temporary output file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
        output_file = temp_file.name
    
    try:
        print("🧪 Testing GitHub Management CLI...")
        print(f"📄 Output will be saved to: {output_file}")
        
        # Test with a well-known public organization (GitHub itself)
        test_org = "github"
        
        # Run the CLI command
        cmd = [sys.executable, cli_script, test_org, output_file, "--verbose"]
        
        print(f"🚀 Running command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ CLI test completed successfully!")
            print("📊 Output:")
            print(result.stdout)
            
            # Try to read and display the output file
            try:
                with open(output_file, 'r') as f:
                    content = f.read()
                    print("📄 Generated JSON content (first 500 chars):")
                    print(content[:500] + "..." if len(content) > 500 else content)
            except Exception as e:
                print(f"⚠️ Could not read output file: {e}")
            
            return True
        else:
            print("❌ CLI test failed!")
            print("📊 STDOUT:")
            print(result.stdout)
            print("📊 STDERR:")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        return False
    
    finally:
        # Clean up temporary file
        try:
            os.unlink(output_file)
        except:
            pass


def main():
    """Main test function."""
    print("GitHub Management CLI Test Suite")
    print("=" * 40)
    
    success = test_cli()
    
    if success:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print("\n💥 Tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
