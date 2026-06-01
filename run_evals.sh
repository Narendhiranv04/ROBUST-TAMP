#!/bin/bash

# Configuration
MODEL_ALIAS=$1
REMOTE_URL="http://127.0.0.1:8000"
MAX_REPLANS=10

if [ -z "$MODEL_ALIAS" ]; then
    echo "Usage: ./run_evals.sh <model_alias>"
    echo "Example: ./run_evals.sh llama-3.3-70b"
    exit 1
fi

echo "======================================================"
echo "Starting Evaluation Suite for Model: $MODEL_ALIAS"
echo "======================================================"

# The environments (Kitchen 1-3, Grill 1-3)
VARIANTS=("K1" "K2" "K3" "G1" "G2" "G3")

# The settings from your table
# "off" = LLM direct execution (first-plan-only)
# "on"  = LLM with replanning
MODES=("off" "on")

for MODE in "${MODES[@]}"; do
    if [ "$MODE" = "off" ]; then
        SETTING_NAME="Direct_Execution"
    else
        SETTING_NAME="Replanning"
    fi
    
    echo ""
    echo ">>> Testing Setting: $SETTING_NAME <<<"
    echo "------------------------------------------------------"

    for VARIANT in "${VARIANTS[@]}"; do
        OUTPUT_DIR="eval_results/${MODEL_ALIAS}/${SETTING_NAME}/${VARIANT}"
        
        echo "Running Variant: $VARIANT"
        
        # We use --headless to ensure it runs fast without popping up Unity windows
        python3 -m llm_pipeline.trial_runner \
            --variant "$VARIANT" \
            --model "$MODEL_ALIAS" \
            --icl-mode zero_shot \
            --remote \
            --remote-url "$REMOTE_URL" \
            --replan-mode "$MODE" \
            --max-replans "$MAX_REPLANS" \
            --headless \
            --output-dir "$OUTPUT_DIR"
            
        echo "Finished $VARIANT. Results saved to $OUTPUT_DIR/record.json"
    done
done

echo ""
echo "======================================================"
echo "Evaluation Suite Complete for $MODEL_ALIAS!"
echo "Check the 'eval_results' folder for your data."
echo "======================================================"
