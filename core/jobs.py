"""Background job management for backtests and optimizations."""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, asdict
from enum import Enum


class JobStatus(Enum):
    """Job execution status."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """Represents a background job."""
    job_id: str
    job_type: str  # "backtest" or "optimization"
    strategy_name: str
    status: str = JobStatus.QUEUED.value
    progress: int = 0  # 0-100
    created_at: str = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result_id: Optional[str] = None  # Reference to result folder
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)


class JobManager:
    """Manages background job execution and tracking."""
    
    def __init__(self, jobs_dir: str = "app/jobs"):
        """Initialize job manager.
        
        Args:
            jobs_dir: Directory to store job metadata
        """
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.jobs: Dict[str, Job] = {}  # In-memory job tracking
        self._load_jobs()
        self._job_queue = []
        self._worker_thread = None
        self._running = False
    
    def _load_jobs(self):
        """Load jobs from disk."""
        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with open(job_file, 'r') as f:
                    job_data = json.load(f)
                    job = Job(**job_data)
                    self.jobs[job.job_id] = job
            except Exception as e:
                print(f"Failed to load job {job_file}: {e}")
    
    def _save_job(self, job: Job):
        """Save job to disk."""
        job_file = self.jobs_dir / f"{job.job_id}.json"
        with open(job_file, 'w') as f:
            json.dump(job.to_dict(), f, indent=2)
    
    def create_job(self, job_id: str, job_type: str, strategy_name: str) -> Job:
        """Create a new job.
        
        Args:
            job_id: Unique job identifier
            job_type: "backtest" or "optimization"
            strategy_name: Name of the strategy
            
        Returns:
            Created Job object
        """
        job = Job(
            job_id=job_id,
            job_type=job_type,
            strategy_name=strategy_name
        )
        self.jobs[job_id] = job
        self._save_job(job)
        return job
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        return self.jobs.get(job_id)
    
    def list_jobs(self, status: Optional[str] = None) -> list:
        """List jobs, optionally filtered by status."""
        jobs = list(self.jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        # Sort by created_at descending
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs
    
    def update_job(self, job_id: str, status: Optional[str] = None, 
                   progress: Optional[int] = None, error: Optional[str] = None,
                   result_id: Optional[str] = None):
        """Update job status/progress."""
        if job_id not in self.jobs:
            return False
        
        job = self.jobs[job_id]
        
        if status:
            job.status = status
            if status == JobStatus.RUNNING.value and not job.started_at:
                job.started_at = datetime.now().isoformat()
            elif status == JobStatus.COMPLETED.value or status == JobStatus.FAILED.value:
                job.completed_at = datetime.now().isoformat()
        
        if progress is not None:
            job.progress = min(100, max(0, progress))
        
        if error:
            job.error = error
        
        if result_id:
            job.result_id = result_id
        
        self._save_job(job)
        return True
    
    def submit_job(self, job_id: str, job_type: str, strategy_name: str,
                   task_func: Callable, task_args: tuple = (),
                   task_kwargs: Dict[str, Any] = None) -> Job:
        """Submit a job for background execution.
        
        Args:
            job_id: Unique job identifier
            job_type: "backtest" or "optimization"
            strategy_name: Name of the strategy
            task_func: Function to execute (should accept job_id as first arg)
            task_args: Additional positional arguments for task_func
            task_kwargs: Keyword arguments for task_func
            
        Returns:
            Created Job object
        """
        if task_kwargs is None:
            task_kwargs = {}
        
        # Create job record
        job = self.create_job(job_id, job_type, strategy_name)
        
        # Add to queue
        self._job_queue.append((job_id, task_func, task_args, task_kwargs))
        
        # Start worker thread if not running
        if not self._running:
            self._running = True
            self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker_thread.start()
        
        return job
    
    def _worker_loop(self):
        """Process jobs from queue."""
        while self._running:
            if not self._job_queue:
                continue
            
            job_id, task_func, task_args, task_kwargs = self._job_queue.pop(0)
            
            try:
                self.update_job(job_id, status=JobStatus.RUNNING.value)
                
                # Execute task - task_func should accept job_id and job_manager
                # and periodically call update_job() to report progress
                result = task_func(job_id, self, *task_args, **task_kwargs)
                
                self.update_job(job_id, status=JobStatus.COMPLETED.value, 
                               progress=100, result_id=result)
                
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                self.update_job(job_id, status=JobStatus.FAILED.value, error=error_msg)
                print(f"Job {job_id} failed: {error_msg}")
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued job."""
        job = self.get_job(job_id)
        if not job:
            return False
        
        if job.status == JobStatus.QUEUED.value:
            # Remove from queue if still queued
            self._job_queue = [(jid, f, a, k) for jid, f, a, k in self._job_queue 
                               if jid != job_id]
            self.update_job(job_id, status=JobStatus.CANCELLED.value)
            return True
        
        return False
    
    def delete_job(self, job_id: str) -> bool:
        """Delete a job from tracking and disk."""
        if job_id not in self.jobs:
            return False
        
        # Remove from memory
        del self.jobs[job_id]
        
        # Remove from disk
        job_file = self.jobs_dir / f"{job_id}.json"
        if job_file.exists():
            job_file.unlink()
        
        return True
    
    def clear_old_jobs(self, days: int = 1):
        """Clear job records older than specified days."""
        from datetime import timedelta
        
        cutoff = datetime.now() - timedelta(days=days)
        jobs_to_delete = []
        
        for job_id, job in self.jobs.items():
            try:
                created = datetime.fromisoformat(job.created_at)
                if created < cutoff:
                    jobs_to_delete.append(job_id)
            except Exception:
                continue
        
        for job_id in jobs_to_delete:
            self.delete_job(job_id)
        
        return len(jobs_to_delete)
