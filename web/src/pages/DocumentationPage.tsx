import { useState } from 'react'
import { Card, PageHeader, Spinner, StateMessage, Badge } from '../components/ui'
import { useMkc, useQuery } from '../state'
import { getApiBase } from '../lib/api'

type GeneratedDocument = {
  id: string
  title: string
  doc_type: string
  content: string
  source_ko_ids: string[]
  version: number
  author: string
  created_at: string
  updated_at: string
  previous_version_id?: string
}

export function DocumentationPage() {
  const { key } = useMkc()
  const [selectedDoc, setSelectedDoc] = useState<GeneratedDocument | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)

  const { loading, error, data: documents, reload } = useQuery<GeneratedDocument[]>(
    async () => {
      const base = getApiBase()
      const res = await fetch(`${base}/documentation/documents`)
      if (!res.ok) throw new Error('Failed to fetch documents')
      return res.json()
    },
    [key],
    key
  )

  const handleGenerate = async (docType: string, topic?: string) => {
    setIsGenerating(true)
    try {
      const base = getApiBase()
      const url = topic 
        ? `${base}/documentation/generate?doc_type=${docType}&topic=${encodeURIComponent(topic)}`
        : `${base}/documentation/generate?doc_type=${docType}`
      const res = await fetch(url, { method: 'POST' })
      if (!res.ok) throw new Error('Failed to generate document')
      await res.json()
      reload()
    } catch (err) {
      console.error('Generation failed:', err)
      alert('Failed to generate document')
    } finally {
      setIsGenerating(false)
    }
  }

  const handleRegenerate = async (documentId: string) => {
    if (!confirm('Create a new version of this document?')) return
    try {
      const base = getApiBase()
      const res = await fetch(`${base}/documentation/documents/${documentId}/regenerate`, { method: 'POST' })
      if (!res.ok) throw new Error('Failed to regenerate document')
      await res.json()
      reload()
    } catch (err) {
      console.error('Regeneration failed:', err)
      alert('Failed to regenerate document')
    }
  }

  if (loading) return <Spinner />
  if (error) return <StateMessage title="Error" detail={error} tone="danger" />

  const docTypes = [
    { id: 'overview', label: 'Overview', icon: '📊' },
    { id: 'api_reference', label: 'API Reference', icon: '📚' },
    { id: 'architecture', label: 'Architecture', icon: '🏗️' },
    { id: 'guide', label: 'Guide', icon: '📖' },
    { id: 'changelog', label: 'Changelog', icon: '📝' }
  ]

  return (
    <div className="documentation-page">
      <PageHeader title="Documentation Library" subtitle="AI-generated documentation from knowledge objects" />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Document List */}
        <div className="lg:col-span-1">
          <Card>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Documents</h3>
              <span className="text-sm text-gray-500">{documents?.length || 0} items</span>
            </div>

            {/* Quick Generate Buttons */}
            <div className="mb-4 p-4 bg-gray-50 rounded-lg">
              <h4 className="text-sm font-medium mb-2">Generate New</h4>
              <div className="grid grid-cols-2 gap-2">
                {docTypes.map(dt => (
                  <button
                    key={dt.id}
                    onClick={() => dt.id === 'guide' 
                      ? handleGenerate(dt.id, prompt('Enter guide topic:') || 'general')
                      : handleGenerate(dt.id)
                    }
                    disabled={isGenerating}
                    className="px-3 py-2 text-sm bg-white border rounded hover:bg-gray-100 disabled:opacity-50"
                  >
                    {dt.icon} {dt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Document List */}
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {documents && documents.length > 0 ? (
                documents.map(doc => (
                  <div
                    key={doc.id}
                    onClick={() => setSelectedDoc(doc)}
                    className={`p-3 rounded cursor-pointer transition ${
                      selectedDoc?.id === doc.id ? 'bg-blue-50 border-blue-200' : 'hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <h4 className="font-medium text-sm truncate">{doc.title}</h4>
                        <div className="flex items-center gap-2 mt-1">
                          <Badge tone="info">{doc.doc_type}</Badge>
                          <span className="text-xs text-gray-500">v{doc.version}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-8 text-gray-500 text-sm">
                  No documents yet. Generate one to get started.
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* Document Viewer */}
        <div className="lg:col-span-2">
          {selectedDoc ? (
            <Card>
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h2 className="text-xl font-semibold">{selectedDoc.title}</h2>
                  <div className="flex items-center gap-2 mt-1">
                    <Badge tone="info">{selectedDoc.doc_type}</Badge>
                    <span className="text-sm text-gray-500">Version {selectedDoc.version}</span>
                    <span className="text-sm text-gray-500">
                      Updated {new Date(selectedDoc.updated_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => handleRegenerate(selectedDoc.id)}
                  className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
                >
                  Regenerate
                </button>
              </div>

              <div className="prose prose-sm max-w-none">
                <div 
                  className="markdown-content"
                  dangerouslySetInnerHTML={{ 
                    __html: selectedDoc.content
                      .replace(/\n/g, '<br>')
                      .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
                      .replace(/`([^`]+)`/g, '<code>$1</code>')
                      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
                      .replace(/\*([^*]+)\*/g, '<em>$1</em>')
                      .replace(/^## (.+)$/gm, '<h3>$1</h3>')
                      .replace(/^# (.+)$/gm, '<h2>$1</h2>')
                      .replace(/^- (.+)$/gm, '<li>$1</li>')
                  }}
                />
              </div>

              <div className="mt-6 pt-4 border-t">
                <h4 className="text-sm font-medium mb-2">Source Knowledge Objects</h4>
                <p className="text-sm text-gray-600">
                  Generated from {selectedDoc.source_ko_ids.length} knowledge objects
                </p>
              </div>
            </Card>
          ) : (
            <Card>
              <div className="text-center py-12 text-gray-500">
                <div className="text-4xl mb-4">📄</div>
                <p>Select a document to view its content</p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
