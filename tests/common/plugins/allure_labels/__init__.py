import allure
import logging
import yaml
import os

logger = logging.getLogger(__name__)

# Load label configuration
def load_label_config():
    """Load label configuration from YAML file"""
    config_path = os.path.join(os.path.dirname(__file__), 'label_config.yaml')
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning(f"Label config file not found at {config_path}")
        return {}
    except Exception as e:
        logger.error(f"Error loading label config: {e}")
        return {}

LABEL_CONFIG = load_label_config()


def pytest_configure(config):
    """Register the plugin and configure Allure labels"""
    config.addinivalue_line("markers", "allure_label(name, value): Add custom Allure label")

def pytest_runtest_logstart(nodeid, location):
    """Add labels when test logging starts (including skipped tests)"""
    add_custom_allure_labels_from_nodeid(nodeid)

def add_custom_allure_labels_from_nodeid(nodeid):
    """Add custom allure labels based on nodeid"""
    test_path = nodeid
    feature_mapping = LABEL_CONFIG.get('feature_mapping', {})

    # Extract the directory path from the test path
    file_path = test_path.split('::')[0]
    path_parts = file_path.split('/')
    print(f"PATH_PARTS:{path_parts}")
    if len(path_parts) > 1:
        # Remove the filename (last part) to get directory path
        dir_parts = path_parts[:-1]
        print(f"DIR_PARTS:{dir_parts}")

        # Try to match nested directory structures
        # First try the full directory path (e.g., "platform_tests.api")
        # Skip the first part (usually "tests") and join the rest
        if len(dir_parts) > 1:
            full_path = '.'.join(dir_parts[:])  # Skip "tests" prefix
            print(f"FULL_PATH:{full_path}")
            if full_path in feature_mapping:
                allure.dynamic.label("feature", feature_mapping[full_path])
                return

        # Then try the immediate parent directory (e.g., "api")
        immediate_parent = dir_parts[-1]
        print(f"IMMEDIATE_PARENT:{immediate_parent}")
        if immediate_parent in feature_mapping:
            allure.dynamic.label("feature", feature_mapping[immediate_parent])
            return

        # If no match found, use "unspecified"
        print(f"ASSIGNING UNSPECIFIED feature label - immediate_parent:{immediate_parent} dir_parts:{dir_parts} path_parts:{path_parts}")
        allure.dynamic.label("feature", "unspecified")
    elif len(path_parts) == 1:
        allure.dynamic.label("feature", "base")

