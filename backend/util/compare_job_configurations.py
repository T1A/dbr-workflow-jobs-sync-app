def compare_job_configurations(job_config1: dict, job_config2: dict) -> tuple[bool, list]:
    """
    Compare two job configurations and return if they're different and a list of differences.
    
    Args:
        job_config1: First job configuration dictionary
        job_config2: Second job configuration dictionary
        
    Returns: 
        tuple[bool, list]: (is_different: bool, differences: list)
            is_different: True if configurations are different
            differences: List of string descriptions of differences, limited to first 10

        Ignores differences in job_id, created_time, and creator_user_name
        Special handling for run_as vs run_as_user_name to avoid false differences
    """
    differences = []
    
    def compare_dict(dict1, dict2, path=""):
        # Special handling for run_as vs run_as_user_name at top level
        if not path:  # Only at top level
            run_as_user_name1 = dict1.get('run_as_user_name')
            run_as_user_name2 = dict2.get('run_as_user_name')
            run_as1 = dict1.get('settings', {}).get('run_as', {})
            run_as2 = dict2.get('settings', {}).get('run_as', {})
            
            # If both have run_as_user_name and one has matching run_as, ignore the run_as difference
            if run_as_user_name1 and run_as_user_name2 and run_as_user_name1 == run_as_user_name2:
                if run_as1.get('user_name') == run_as_user_name1:
                    dict1.get('settings', {}).pop('run_as', None)
                if run_as2.get('user_name') == run_as_user_name2:
                    dict2.get('settings', {}).pop('run_as', None)

        if isinstance(dict1, list) and isinstance(dict2, list):
            # Compare lists
            for i in range(max(len(dict1), len(dict2))):
                if i >= len(dict1):
                    differences.append(f"{path}[{i}]: (added) → {dict2[i]}")
                elif i >= len(dict2):
                    differences.append(f"{path}[{i}]: {dict1[i]} → (removed)")
                else:
                    compare_dict(dict1[i], dict2[i], f"{path}[{i}]")
            return
        
        if not isinstance(dict1, dict) or not isinstance(dict2, dict):
            if dict1 != dict2:
                differences.append(f"{path}: {dict1} → {dict2}")
            return
            
        for key in set(dict1.keys()) | set(dict2.keys()):
            current_path = f"{path}.{key}" if path else key

            if key in ('job_id', 'created_time', 'creator_user_name'):
                continue

            # Key exists in both
            if key in dict1 and key in dict2:
                if isinstance(dict1[key], dict) and isinstance(dict2[key], dict):
                    compare_dict(dict1[key], dict2[key], current_path)
                elif isinstance(dict1[key], list) and isinstance(dict2[key], list):
                    compare_dict(dict1[key], dict2[key], current_path)
                elif dict1[key] != dict2[key]:
                    differences.append(f"{current_path}: {dict1[key]} → {dict2[key]}")
            # Key only in dict1
            elif key in dict1:
                differences.append(f"{current_path}: {dict1[key]} → (removed)")
            # Key only in dict2
            else:
                differences.append(f"{current_path}: (added) → {dict2[key]}")
    
    # Create deep copies to avoid modifying the original dicts
    import copy
    dict1_copy = copy.deepcopy(job_config1)
    dict2_copy = copy.deepcopy(job_config2)
    
    compare_dict(dict1_copy, dict2_copy)

    return bool(differences), differences[:10]  # Limit to first 10 differences