import subprocess
import json
import os
from pathlib import Path
import glob

def run_trials_and_aggregate():
    model_alias = "deepseek-r1-qwen-14b"
    variant = "K3"
    num_trials = 10
    remote_url = "http://127.0.0.1:8000"
    output_dir = f"eval_results_10_trials/{model_alias}/{variant}"
    
    print(f"Starting {num_trials} trials for {variant} using {model_alias}...")
    
    # Run the trials
    for i in range(1, num_trials + 1):
        print(f"\n--- Running Trial {i}/{num_trials} ---")
        trial_output_dir = os.path.join(output_dir, f"trial_{i:03d}")
        
        cmd = [
            "python", "-m", "llm_pipeline.trial_runner",
            "--variant", variant,
            "--model", model_alias,
            "--icl-mode", "zero_shot",
            "--remote",
            "--remote-url", remote_url,
            "--max-replans", "10",
            "--headless", # crucial for fast automated runs
            "--output-dir", trial_output_dir
        ]
        
        # Run the command and wait for it to finish
        subprocess.run(cmd, check=False)
        print(f"Finished Trial {i}. Results saved to {trial_output_dir}")

    # Aggregate metrics
    print("\n===========================================")
    print("Aggregating Metrics...")
    
    record_files = glob.glob(f"{output_dir}/**/record.json", recursive=True)
    
    if not record_files:
        print("No record.json files found. Did the trials fail to run?")
        return

    total_successes = 0
    total_subtask_coverage = 0.0
    total_time = 0.0
    total_replans = 0
    
    valid_trials = 0
    
    for record_file in record_files:
        with open(record_file, 'r') as f:
            try:
                data = json.load(f)
                
                total_successes += 1 if data.get("episode_success", False) else 0
                total_subtask_coverage += data.get("subtask_completion_rate", 0.0)
                total_time += data.get("episode_time_s", 0.0)
                total_replans += data.get("total_replans", 0)
                
                valid_trials += 1
            except Exception as e:
                print(f"Error reading {record_file}: {e}")
                
    if valid_trials == 0:
        print("No valid data to aggregate.")
        return
        
    mean_task_success = total_successes / valid_trials
    mean_subtask_coverage = total_subtask_coverage / valid_trials
    avg_time = total_time / valid_trials
    avg_replans = total_replans / valid_trials
    
    print("===========================================")
    print(f"RESULTS FOR {model_alias} - {variant} ({valid_trials} trials)")
    print("===========================================")
    print(f"Mean Task Success:     {mean_task_success * 100:.1f} ({total_successes}/{valid_trials})")
    print(f"Mean Subtask Coverage: {mean_subtask_coverage * 100:.1f}")
    print(f"Avg. Time (s):         {avg_time:.2f}")
    print(f"Avg. Replans:          {avg_replans:.2f}")
    print("===========================================")
    
    # LaTeX formatted string
    print("\nLaTeX Table String:")
    print(f"& {mean_task_success * 100:.1f} & {mean_subtask_coverage * 100:.1f} & {avg_time:.1f} & {avg_replans:.1f} \\\\")

if __name__ == "__main__":
    run_trials_and_aggregate()
