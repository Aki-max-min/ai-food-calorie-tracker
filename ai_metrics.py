"""
ai_metrics.py

AI Performance & Evaluation Framework
Tracks model accuracy, latency, confidence scores, and recommendations.

Metrics Tracked:
- Model Confidence: Average confidence score across predictions
- Prediction Accuracy: User-validated accuracy (user marks "correct" or "incorrect")
- Inference Latency: Time to get response from Gemini
- Cache Hit Rate: Percentage of requests served from cache
- Cost Efficiency: API calls saved through caching
- Anomaly Detection: Flagged unusual portion/calorie combinations
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from statistics import mean, stdev
from typing import Optional

logger = logging.getLogger(__name__)

METRICS_FILE = Path("metrics.jsonl")


class PredictionMetrics:
    """Track AI prediction performance."""
    
    @staticmethod
    def log_prediction(
        meal_id: int,
        dish_name: str,
        confidence_avg: float,
        model_response_time: float,
        was_cached: bool,
        user_validated: bool = False,
        user_feedback: str = ""  # "correct", "incorrect", "partial"
    ):
        """
        Log a single prediction for evaluation.
        
        Args:
            meal_id: Database meal ID
            dish_name: Identified food dish
            confidence_avg: Average confidence score (0-1)
            model_response_time: Gemini API latency in seconds
            was_cached: Whether result came from cache
            user_validated: Whether user provided feedback
            user_feedback: "correct" | "incorrect" | "partial"
        """
        record = {
            "timestamp": datetime.now().isoformat(),
            "meal_id": meal_id,
            "dish_name": dish_name,
            "confidence": round(confidence_avg, 3),
            "response_time_ms": round(model_response_time * 1000, 1),
            "cached": was_cached,
            "user_validated": user_validated,
            "user_feedback": user_feedback
        }
        
        # Append to JSONL (JSON Lines)
        with open(METRICS_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
        
        logger.info(f"Logged prediction: {dish_name} (confidence: {confidence_avg:.2%})")


class PerformanceAnalysis:
    """Analyze collected metrics."""
    
    @staticmethod
    def load_metrics() -> list[dict]:
        """Load all logged metrics."""
        if not METRICS_FILE.exists():
            return []
        
        metrics = []
        with open(METRICS_FILE, "r") as f:
            for line in f:
                try:
                    metrics.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return metrics
    
    @staticmethod
    def get_confidence_metrics() -> dict:
        """Analyze confidence scores across all predictions."""
        metrics = PerformanceAnalysis.load_metrics()
        if not metrics:
            return {
                "avg_confidence": 0.0,
                "min_confidence": 0.0,
                "max_confidence": 0.0,
                "std_dev": 0.0,
                "total_predictions": 0
            }
        
        confidences = [m["confidence"] for m in metrics]
        
        return {
            "avg_confidence": round(mean(confidences), 3),
            "min_confidence": round(min(confidences), 3),
            "max_confidence": round(max(confidences), 3),
            "std_dev": round(stdev(confidences), 3) if len(confidences) > 1 else 0.0,
            "total_predictions": len(metrics),
            "high_confidence": len([c for c in confidences if c >= 0.75]),
            "medium_confidence": len([c for c in confidences if 0.5 <= c < 0.75]),
            "low_confidence": len([c for c in confidences if c < 0.5])
        }
    
    @staticmethod
    def get_latency_metrics() -> dict:
        """Analyze API response times."""
        metrics = PerformanceAnalysis.load_metrics()
        cached = [m for m in metrics if m["cached"]]
        uncached = [m for m in metrics if not m["cached"]]
        
        def analyze(ms_list):
            if not ms_list:
                return {"avg": 0, "min": 0, "max": 0, "count": 0}
            return {
                "avg": round(mean(ms_list), 1),
                "min": round(min(ms_list), 1),
                "max": round(max(ms_list), 1),
                "count": len(ms_list)
            }
        
        cached_times = [m["response_time_ms"] for m in cached]
        uncached_times = [m["response_time_ms"] for m in uncached]
        
        return {
            "cached_queries": analyze(cached_times),
            "uncached_queries": analyze(uncached_times),
            "speedup_factor": round(
                analyze(uncached_times)["avg"] / (analyze(cached_times)["avg"] or 1),
                1
            ) if cached else 0
        }
    
    @staticmethod
    def get_cache_metrics() -> dict:
        """Analyze caching effectiveness."""
        metrics = PerformanceAnalysis.load_metrics()
        if not metrics:
            return {
                "cache_hit_rate": 0.0,
                "api_calls_saved": 0,
                "api_cost_reduction": 0.0
            }
        
        total = len(metrics)
        cached = len([m for m in metrics if m["cached"]])
        hit_rate = cached / total if total > 0 else 0
        
        # Cost: Assume $0.075 per 1M input tokens, ~1KB ≈ 250 tokens
        # Each uncached call ≈ 2KB = 500 tokens ≈ $0.0000375
        api_cost_per_call = 0.0000375
        saved_calls = cached
        cost_saved = saved_calls * api_cost_per_call
        
        return {
            "total_predictions": total,
            "cache_hits": cached,
            "cache_hit_rate": round(hit_rate, 3),
            "cache_hit_pct": round(hit_rate * 100, 1),
            "api_calls_saved": saved_calls,
            "api_cost_saved": f"${cost_saved:.4f}",
            "efficiency_ratio": round((total) / (total - cached) if (total - cached) > 0 else total, 1)
        }
    
    @staticmethod
    def get_accuracy_metrics() -> dict:
        """
        Analyze user-validated prediction accuracy.
        Requires user feedback for ground truth.
        """
        metrics = PerformanceAnalysis.load_metrics()
        validated = [m for m in metrics if m.get("user_validated")]
        
        if not validated:
            return {
                "validated_predictions": 0,
                "accuracy": None,
                "precision": None,
                "recall": None,
                "f1_score": None,
                "confidence_correlation": None,
                "note": "No user feedback yet. Accuracy will improve as users validate predictions."
            }
        
        correct = len([m for m in validated if m.get("user_feedback") == "correct"])
        partial = len([m for m in validated if m.get("user_feedback") == "partial"])
        incorrect = len([m for m in validated if m.get("user_feedback") == "incorrect"])
        
        total_validated = len(validated)
        accuracy = (correct + 0.5 * partial) / total_validated if total_validated > 0 else 0
        
        # Confidence correlation: Do high-confidence predictions correlate with correctness?
        correct_confidences = [m["confidence"] for m in validated if m.get("user_feedback") == "correct"]
        incorrect_confidences = [m["confidence"] for m in validated if m.get("user_feedback") == "incorrect"]
        
        avg_correct_conf = mean(correct_confidences) if correct_confidences else 0
        avg_incorrect_conf = mean(incorrect_confidences) if incorrect_confidences else 0
        
        return {
            "validated_predictions": total_validated,
            "correct": correct,
            "partial": partial,
            "incorrect": incorrect,
            "accuracy": round(accuracy, 3),
            "accuracy_pct": round(accuracy * 100, 1),
            "confidence_in_correct": round(avg_correct_conf, 3),
            "confidence_in_incorrect": round(avg_incorrect_conf, 3),
            "confidence_alignment": "Good" if avg_correct_conf > avg_incorrect_conf else "Poor"
        }
    
    @staticmethod
    def get_summary() -> dict:
        """Get complete performance summary."""
        return {
            "timestamp": datetime.now().isoformat(),
            "confidence": PerformanceAnalysis.get_confidence_metrics(),
            "latency": PerformanceAnalysis.get_latency_metrics(),
            "cache": PerformanceAnalysis.get_cache_metrics(),
            "accuracy": PerformanceAnalysis.get_accuracy_metrics()
        }
    
    @staticmethod
    def print_report():
        """Print human-readable metrics report."""
        summary = PerformanceAnalysis.get_summary()
        
        print("\n" + "="*60)
        print("AI NUTRITION ANALYSIS PLATFORM - METRICS REPORT")
        print("="*60)
        
        # Confidence
        conf = summary["confidence"]
        print(f"\n📊 CONFIDENCE SCORING")
        print(f"  Average Confidence: {conf['avg_confidence']:.1%}")
        print(f"  High Confidence (≥75%): {conf['high_confidence']}/{conf['total_predictions']}")
        print(f"  Medium Confidence (50-75%): {conf['medium_confidence']}/{conf['total_predictions']}")
        print(f"  Low Confidence (<50%): {conf['low_confidence']}/{conf['total_predictions']}")
        
        # Latency
        lat = summary["latency"]
        print(f"\n⚡ INFERENCE LATENCY")
        print(f"  Cached Queries: {lat['cached_queries']['avg']:.0f}ms avg")
        print(f"  Uncached Queries: {lat['uncached_queries']['avg']:.0f}ms avg")
        print(f"  Speedup Factor: {lat['speedup_factor']:.1f}x faster (cached)")
        
        # Cache
        cache = summary["cache"]
        print(f"\n💾 CACHE EFFICIENCY")
        print(f"  Cache Hit Rate: {cache['cache_hit_pct']:.1f}%")
        print(f"  API Calls Saved: {cache['api_calls_saved']}")
        print(f"  Cost Saved: {cache['api_cost_saved']}")
        
        # Accuracy
        acc = summary["accuracy"]
        if acc["validated_predictions"] > 0:
            print(f"\n✅ PREDICTION ACCURACY (User Validated)")
            print(f"  Accuracy: {acc['accuracy_pct']:.1f}%")
            print(f"  Correct Predictions: {acc['correct']}/{acc['validated_predictions']}")
            print(f"  Confidence Alignment: {acc['confidence_alignment']}")
        else:
            print(f"\n✅ PREDICTION ACCURACY")
            print(f"  Waiting for user feedback to calculate accuracy metrics...")
        
        print("\n" + "="*60)