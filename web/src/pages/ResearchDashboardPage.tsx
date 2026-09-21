import { useState } from 'react'
import { Card, PageHeader, Spinner, StateMessage, Badge } from '../components/ui'
import { useMkc, useQuery } from '../state'
import { getApiBase } from '../lib/api'

type ScheduledTask = {
  id: string
  name: string
  task_type: string
  schedule: string
  enabled: boolean
  last_run: string | null
  next_run: string | null
  run_count: number
  metadata: Record<string, any>
}

type TaskExecution = {
  id: string
  task_id: string | null
  task_type: string
  status: string
  findings: string[]
  insights_generated: number
  contradictions_found: number
  hypotheses_generated: number
  error_message: string | null
  started_at: string
  completed_at: string | null
}

export function ResearchDashboardPage() {
  const { key } = useMkc()
  const [selectedTab, setSelectedTab] = useState<'scheduled' | 'executions'>('scheduled')
  const [isRunning, setIsRunning] = useState(false)

  const { loading: tasksLoading, error: tasksError, data: tasks, reload: reloadTasks } = useQuery<ScheduledTask[]>(
    async () => {
      const base = getApiBase()
      const res = await fetch(`${base}/research-tasks/scheduled`)
      if (!res.ok) throw new Error('Failed to fetch scheduled tasks')
      return res.json()
    },
    [key],
    key
  )

  const { loading: executionsLoading, error: executionsError, data: executions, reload: reloadExecutions } = useQuery<TaskExecution[]>(
    async () => {
      const base = getApiBase()
      const res = await fetch(`${base}/research-tasks/executions`)
      if (!res.ok) throw new Error('Failed to fetch executions')
      return res.json()
    },
    [key],
    key
  )

  const handleRunTask = async (taskType: string) => {
    setIsRunning(true)
    try {
      const base = getApiBase()
      const res = await fetch(`${base}/research-tasks/run?task_type=${taskType}`, { method: 'POST' })
      if (!res.ok) throw new Error('Failed to run task')
      await res.json()
      reloadExecutions()
    } catch (err) {
      console.error('Task run failed:', err)
      alert('Failed to run task')
    } finally {
      setIsRunning(false)
    }
  }

  const handleToggleTask = async (taskId: string, currentEnabled: boolean) => {
    try {
      const base = getApiBase()
      const res = await fetch(`${base}/research-tasks/scheduled/${taskId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !currentEnabled })
      })
      if (!res.ok) throw new Error('Failed to update task')
      await res.json()
      reloadTasks()
    } catch (err) {
      console.error('Task update failed:', err)
      alert('Failed to update task')
    }
  }

  if (tasksLoading || executionsLoading) return <Spinner />
  if (tasksError || executionsError) return <StateMessage title="Error" detail={tasksError || executionsError} tone="danger" />

  const taskTypes = [
    { id: 'analyze_gaps', label: 'Analyze Gaps', description: 'Identify research gaps in knowledge objects' },
    { id: 'generate_hypotheses', label: 'Generate Hypotheses', description: 'Propose new research hypotheses' },
    { id: 'synthesis', label: 'Synthesis', description: 'Synthesize information across sources' },
    { id: 'contradiction_deep_dive', label: 'Contradiction Deep Dive', description: 'Analyze flagged contradictions' },
    { id: 'cross_source_analysis', label: 'Cross-Source Analysis', description: 'Analyze knowledge across sources' }
  ]

  return (
    <div className="research-dashboard-page">
      <PageHeader title="Research Dashboard" subtitle="Scheduled research workflows and AI-assisted analysis" />

      <div className="mb-6">
        <div className="flex gap-2">
          <button
            onClick={() => setSelectedTab('scheduled')}
            className={`px-4 py-2 rounded ${selectedTab === 'scheduled' ? 'bg-blue-600 text-white' : 'bg-gray-200'}`}
          >
            Scheduled Tasks
          </button>
          <button
            onClick={() => setSelectedTab('executions')}
            className={`px-4 py-2 rounded ${selectedTab === 'executions' ? 'bg-blue-600 text-white' : 'bg-gray-200'}`}
          >
            Execution History
          </button>
        </div>
      </div>

      {selectedTab === 'scheduled' ? (
        <div className="space-y-4">
          <Card>
            <h3 className="text-lg font-semibold mb-4">Run Research Task</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {taskTypes.map(tt => (
                <button
                  key={tt.id}
                  onClick={() => handleRunTask(tt.id)}
                  disabled={isRunning}
                  className="p-4 text-left border rounded hover:bg-gray-50 disabled:opacity-50"
                >
                  <div className="font-medium">{tt.label}</div>
                  <div className="text-sm text-gray-600 mt-1">{tt.description}</div>
                </button>
              ))}
            </div>
          </Card>

          <Card>
            <h3 className="text-lg font-semibold mb-4">Scheduled Tasks</h3>
            {tasks && tasks.length > 0 ? (
              <div className="space-y-3">
                {tasks.map(task => (
                  <div key={task.id} className="p-4 border rounded">
                    <div className="flex items-start justify-between">
                      <div>
                        <h4 className="font-medium">{task.name}</h4>
                        <div className="flex items-center gap-2 mt-1">
                          <Badge tone={task.enabled ? 'ok' : 'neutral'}>{task.task_type}</Badge>
                          <span className="text-sm text-gray-600">Schedule: {task.schedule}</span>
                        </div>
                        <div className="text-sm text-gray-500 mt-1">
                          Run count: {task.run_count} | Last run: {task.last_run ? new Date(task.last_run).toLocaleString() : 'Never'}
                        </div>
                      </div>
                      <button
                        onClick={() => handleToggleTask(task.id, task.enabled)}
                        className={`px-3 py-1 text-sm rounded ${task.enabled ? 'bg-green-600 text-white' : 'bg-gray-300'}`}
                      >
                        {task.enabled ? 'Enabled' : 'Disabled'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500">No scheduled tasks configured</div>
            )}
          </Card>
        </div>
      ) : (
        <Card>
          <h3 className="text-lg font-semibold mb-4">Execution History</h3>
          {executions && executions.length > 0 ? (
            <div className="space-y-3">
              {executions.map(exec => (
                <div key={exec.id} className="p-4 border rounded">
                  <div className="flex items-start justify-between">
                    <div>
                      <h4 className="font-medium">{exec.task_type}</h4>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge tone={exec.status === 'completed' ? 'ok' : exec.status === 'failed' ? 'danger' : 'info'}>
                          {exec.status}
                        </Badge>
                        <span className="text-sm text-gray-600">
                          {new Date(exec.started_at).toLocaleString()}
                        </span>
                      </div>
                      <div className="text-sm text-gray-500 mt-1">
                        Insights: {exec.insights_generated} | Contradictions: {exec.contradictions_found} | Hypotheses: {exec.hypotheses_generated}
                      </div>
                    </div>
                  </div>
                  {exec.findings && exec.findings.length > 0 && (
                    <div className="mt-3 pt-3 border-t">
                      <div className="text-sm font-medium mb-1">Findings:</div>
                      <div className="text-sm text-gray-600 max-h-32 overflow-y-auto">
                        {exec.findings.map((finding, idx) => (
                          <div key={idx} className="mb-1">• {finding.substring(0, 200)}...</div>
                        ))}
                      </div>
                    </div>
                  )}
                  {exec.error_message && (
                    <div className="mt-3 pt-3 border-t text-sm text-red-600">
                      Error: {exec.error_message}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500">No execution history</div>
          )}
        </Card>
      )}
    </div>
  )
}
