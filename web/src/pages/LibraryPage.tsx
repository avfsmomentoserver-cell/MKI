import { useState } from 'react'
import { Card, PageHeader, Spinner, StateMessage, Badge } from '../components/ui'
import { useMkc, useQuery } from '../state'
import { getApiBase } from '../lib/api'

type LibraryMetrics = {
  total_knowledge_objects: number
  total_documents: number
  total_sources: number
  total_generated_documents: number
  total_generated_books: number
  total_insights: number
  total_contradictions: number
  ko_type_distribution: Record<string, number>
  document_type_distribution: Record<string, number>
  lifecycle_distribution: Record<string, number>
  knowledge_objects_last_7_days: number
  knowledge_objects_last_30_days: number
  average_confidence: number
  high_confidence_count: number
  low_confidence_count: number
  avg_doc_chapters: number
  avg_book_chapters: number
  metadata: Record<string, any>
}

type GraphNode = {
  id: string
  label: string
  type: string
  properties: Record<string, any>
  source_ko_id: string | null
}

type GraphEdge = {
  id: string
  source: string
  target: string
  label: string
  weight: number
  properties: Record<string, any>
}

type GraphData = {
  nodes: GraphNode[]
  edges: GraphEdge[]
  metadata: Record<string, any>
}

type TopSource = {
  source_id: string
  source_type: string
  source_id_str: string
  ko_count: number
  indexed_at: string | null
}

export function LibraryPage() {
  const { key } = useMkc()
  const [selectedTab, setSelectedTab] = useState<'metrics' | 'graph' | 'sources'>('metrics')

  const { loading: metricsLoading, error: metricsError, data: metrics } = useQuery<LibraryMetrics>(
    async () => {
      const base = getApiBase()
      const res = await fetch(`${base}/library/metrics`)
      if (!res.ok) throw new Error('Failed to fetch metrics')
      return res.json()
    },
    [key],
    key
  )

  const { loading: graphLoading, error: graphError, data: graph } = useQuery<GraphData>(
    async () => {
      const base = getApiBase()
      const res = await fetch(`${base}/library/graph?limit=50`)
      if (!res.ok) throw new Error('Failed to fetch graph')
      return res.json()
    },
    [key],
    key
  )

  const { loading: sourcesLoading, error: sourcesError, data: sources } = useQuery<TopSource[]>(
    async () => {
      const base = getApiBase()
      const res = await fetch(`${base}/library/top-sources?limit=10`)
      if (!res.ok) throw new Error('Failed to fetch sources')
      return res.json()
    },
    [key],
    key
  )

  if (metricsLoading || graphLoading || sourcesLoading) return <Spinner />
  if (metricsError || graphError || sourcesError) return <StateMessage title="Error" detail={metricsError || graphError || sourcesError} tone="danger" />

  return (
    <div className="library-page">
      <PageHeader title="Library Management" subtitle="Analytics, graph visualization, and curation tools" />

      <div className="mb-6">
        <div className="flex gap-2">
          <button
            onClick={() => setSelectedTab('metrics')}
            className={`px-4 py-2 rounded ${selectedTab === 'metrics' ? 'bg-blue-600 text-white' : 'bg-gray-200'}`}
          >
            Metrics
          </button>
          <button
            onClick={() => setSelectedTab('graph')}
            className={`px-4 py-2 rounded ${selectedTab === 'graph' ? 'bg-blue-600 text-white' : 'bg-gray-200'}`}
          >
            Knowledge Graph
          </button>
          <button
            onClick={() => setSelectedTab('sources')}
            className={`px-4 py-2 rounded ${selectedTab === 'sources' ? 'bg-blue-600 text-white' : 'bg-gray-200'}`}
          >
            Top Sources
          </button>
        </div>
      </div>

      {selectedTab === 'metrics' && metrics && (
        <div className="space-y-6">
          <Card>
            <h3 className="text-lg font-semibold mb-4">Overview</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-4 bg-blue-50 rounded">
                <div className="text-2xl font-bold text-blue-600">{metrics.total_knowledge_objects}</div>
                <div className="text-sm text-gray-600">Knowledge Objects</div>
              </div>
              <div className="p-4 bg-green-50 rounded">
                <div className="text-2xl font-bold text-green-600">{metrics.total_documents}</div>
                <div className="text-sm text-gray-600">Documents</div>
              </div>
              <div className="p-4 bg-purple-50 rounded">
                <div className="text-2xl font-bold text-purple-600">{metrics.total_generated_documents}</div>
                <div className="text-sm text-gray-600">Generated Docs</div>
              </div>
              <div className="p-4 bg-orange-50 rounded">
                <div className="text-2xl font-bold text-orange-600">{metrics.total_generated_books}</div>
                <div className="text-sm text-gray-600">Generated Books</div>
              </div>
            </div>
          </Card>

          <Card>
            <h3 className="text-lg font-semibold mb-4">Quality Metrics</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 border rounded">
                <div className="text-sm text-gray-600 mb-1">Average Confidence</div>
                <div className="text-xl font-bold">{(metrics.average_confidence * 100).toFixed(1)}%</div>
              </div>
              <div className="p-4 border rounded">
                <div className="text-sm text-gray-600 mb-1">High Confidence (&gt;80%)</div>
                <div className="text-xl font-bold text-green-600">{metrics.high_confidence_count}</div>
              </div>
              <div className="p-4 border rounded">
                <div className="text-sm text-gray-600 mb-1">Low Confidence (&lt;50%)</div>
                <div className="text-xl font-bold text-red-600">{metrics.low_confidence_count}</div>
              </div>
            </div>
          </Card>

          <Card>
            <h3 className="text-lg font-semibold mb-4">Knowledge Object Types</h3>
            <div className="space-y-2">
              {Object.entries(metrics.ko_type_distribution).map(([type, count]) => (
                <div key={type} className="flex items-center justify-between p-2 border rounded">
                  <span className="font-medium">{type}</span>
                  <Badge tone="info">{count}</Badge>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <h3 className="text-lg font-semibold mb-4">Lifecycle Distribution</h3>
            <div className="space-y-2">
              {Object.entries(metrics.lifecycle_distribution).map(([state, count]) => (
                <div key={state} className="flex items-center justify-between p-2 border rounded">
                  <span className="font-medium">{state}</span>
                  <Badge tone="info">{count}</Badge>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <h3 className="text-lg font-semibold mb-4">Recent Activity</h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 border rounded">
                <div className="text-sm text-gray-600 mb-1">Last 7 Days</div>
                <div className="text-xl font-bold">{metrics.knowledge_objects_last_7_days}</div>
              </div>
              <div className="p-4 border rounded">
                <div className="text-sm text-gray-600 mb-1">Last 30 Days</div>
                <div className="text-xl font-bold">{metrics.knowledge_objects_last_30_days}</div>
              </div>
            </div>
          </Card>
        </div>
      )}

      {selectedTab === 'graph' && graph && (
        <div className="space-y-6">
          <Card>
            <h3 className="text-lg font-semibold mb-4">Knowledge Graph Overview</h3>
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div className="p-4 border rounded">
                <div className="text-sm text-gray-600 mb-1">Nodes</div>
                <div className="text-xl font-bold">{graph.metadata.node_count}</div>
              </div>
              <div className="p-4 border rounded">
                <div className="text-sm text-gray-600 mb-1">Edges</div>
                <div className="text-xl font-bold">{graph.metadata.edge_count}</div>
              </div>
            </div>
            <div className="p-4 bg-gray-50 rounded text-center text-gray-600">
              Graph visualization would go here (requires a graph visualization library like vis.js or d3.js)
            </div>
          </Card>

          <Card>
            <h3 className="text-lg font-semibold mb-4">Node Types</h3>
            <div className="space-y-2">
              {Object.entries(
                graph.nodes.reduce((acc, node) => {
                  acc[node.type] = (acc[node.type] || 0) + 1
                  return acc
                }, {} as Record<string, number>)
              ).map(([type, count]) => (
                <div key={type} className="flex items-center justify-between p-2 border rounded">
                  <span className="font-medium">{type}</span>
                  <Badge tone="info">{count}</Badge>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {selectedTab === 'sources' && sources && (
        <div className="space-y-6">
          <Card>
            <h3 className="text-lg font-semibold mb-4">Top Sources by Knowledge Objects</h3>
            <div className="space-y-3">
              {sources.map((source, idx) => (
                <div key={source.source_id} className="p-4 border rounded">
                  <div className="flex items-start justify-between">
                    <div>
                      <h4 className="font-medium">{source.source_id_str}</h4>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge tone="info">{source.source_type}</Badge>
                        <span className="text-sm text-gray-600">{source.ko_count} KOs</span>
                      </div>
                      {source.indexed_at && (
                        <div className="text-sm text-gray-500 mt-1">
                          Indexed: {new Date(source.indexed_at).toLocaleDateString()}
                        </div>
                      )}
                    </div>
                    <div className="text-lg font-bold text-blue-600">#{idx + 1}</div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}
