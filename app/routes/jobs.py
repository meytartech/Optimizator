"""
Job management routes - queuing, monitoring, and managing background jobs.
"""

from flask import Blueprint, render_template, jsonify, current_app
import logging

logger = logging.getLogger(__name__)
bp = Blueprint('jobs', __name__, url_prefix='')


@bp.route('/jobs')
def jobs_page():
    """Deprecated jobs page - redirect to unified results view."""
    from flask import redirect, url_for
    return redirect(url_for('results.results_page'))


@bp.route('/api/jobs')
def api_list_jobs():
    """Get list of all jobs (JSON API)."""
    job_manager = current_app.job_manager
    jobs = job_manager.list_jobs()
    return jsonify([job.to_dict() for job in jobs])


@bp.route('/api/jobs/<job_id>')
def api_get_job(job_id):
    """Get a specific job (JSON API)."""
    job_manager = current_app.job_manager
    job = job_manager.get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job.to_dict())


@bp.route('/api/jobs/<job_id>/cancel', methods=['POST'])
def api_cancel_job(job_id):
    """Cancel a queued job (JSON API)."""
    job_manager = current_app.job_manager
    if job_manager.cancel_job(job_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Could not cancel job'}), 400


@bp.route('/api/jobs/<job_id>', methods=['DELETE'])
def api_delete_job(job_id):
    """Delete a job (JSON API)."""
    try:
        job_manager = current_app.job_manager
        if job_manager.delete_job(job_id):
            logger.info(f"Deleted job: {job_id}")
            return jsonify({'success': True})
        return jsonify({'error': 'Could not delete job'}), 400
    except Exception as e:
        logger.exception(f"DELETE JOB FAILED: {str(e)}")
        return jsonify({'error': str(e)}), 500
