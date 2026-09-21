import { useState } from 'react'
import { Card, PageHeader, Spinner, StateMessage, Badge } from '../components/ui'
import { useMkc, useQuery } from '../state'
import { getApiBase } from '../lib/api'

type GeneratedBook = {
  id: string
  title: string
  subtitle: string | null
  author: string
  description: string | null
  structure_type: string
  content_markdown: string
  content_html: string | null
  table_of_contents: string | null
  source_ko_ids: string[]
  chapter_count: number
  metadata: Record<string, any>
  created_at: string
  updated_at: string
}

export function BooksPage() {
  const { key } = useMkc()
  const [selectedBook, setSelectedBook] = useState<GeneratedBook | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [exportFormat, setExportFormat] = useState<string>('markdown')

  const { loading, error, data: books, reload } = useQuery<GeneratedBook[]>(
    async () => {
      const base = getApiBase()
      const res = await fetch(`${base}/books/`)
      if (!res.ok) throw new Error('Failed to fetch books')
      return res.json()
    },
    [key],
    key
  )

  const handleGenerateBook = async (title: string, structureType: string) => {
    setIsGenerating(true)
    try {
      const base = getApiBase()
      const res = await fetch(`${base}/books/generate?title=${encodeURIComponent(title)}&structure_type=${structureType}`, { method: 'POST' })
      if (!res.ok) throw new Error('Failed to generate book')
      await res.json()
      reload()
    } catch (err) {
      console.error('Book generation failed:', err)
      alert('Failed to generate book')
    } finally {
      setIsGenerating(false)
    }
  }

  const handleExportBook = async (format: string) => {
    if (!selectedBook) return
    try {
      const base = getApiBase()
      const res = await fetch(`${base}/books/${selectedBook.id}/export/${format}`)
      if (!res.ok) throw new Error('Failed to export book')
      const data = await res.json()
      
      // Create download
      const blob = new Blob([data.content], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = data.filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Export failed:', err)
      alert('Failed to export book')
    }
  }

  const handleDeleteBook = async (bookId: string) => {
    if (!confirm('Delete this book?')) return
    try {
      const base = getApiBase()
      const res = await fetch(`${base}/books/${bookId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('Failed to delete book')
      reload()
      if (selectedBook?.id === bookId) {
        setSelectedBook(null)
      }
    } catch (err) {
      console.error('Delete failed:', err)
      alert('Failed to delete book')
    }
  }

  if (loading) return <Spinner />
  if (error) return <StateMessage title="Error" detail={error} tone="danger" />

  const structureTypes = [
    { id: 'topic_based', label: 'Topic-Based', description: 'Organize by AI-detected topics' },
    { id: 'chronological', label: 'Chronological', description: 'Organize by creation date' },
    { id: 'type_based', label: 'Type-Based', description: 'Organize by knowledge type' }
  ]

  return (
    <div className="books-page">
      <PageHeader title="Book Library" subtitle="Generate and export books from knowledge objects" />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Book Library */}
        <div className="lg:col-span-1">
          <Card>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Books</h3>
              <span className="text-sm text-gray-500">{books?.length || 0} items</span>
            </div>

            {/* Generate New Book */}
            <div className="mb-4 p-4 bg-gray-50 rounded-lg">
              <h4 className="text-sm font-medium mb-2">Generate New Book</h4>
              <div className="space-y-2">
                <input
                  type="text"
                  placeholder="Book title"
                  className="w-full px-3 py-2 border rounded text-sm"
                  id="new-book-title"
                />
                <select className="w-full px-3 py-2 border rounded text-sm" id="new-book-structure">
                  {structureTypes.map(st => (
                    <option key={st.id} value={st.id}>{st.label}</option>
                  ))}
                </select>
                <button
                  onClick={() => {
                    const title = (document.getElementById('new-book-title') as HTMLInputElement).value || 'Knowledge Base'
                    const structure = (document.getElementById('new-book-structure') as HTMLSelectElement).value
                    handleGenerateBook(title, structure)
                  }}
                  disabled={isGenerating}
                  className="w-full px-3 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50"
                >
                  {isGenerating ? 'Generating...' : 'Generate Book'}
                </button>
              </div>
            </div>

            {/* Book List */}
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {books && books.length > 0 ? (
                books.map(book => (
                  <div
                    key={book.id}
                    onClick={() => setSelectedBook(book)}
                    className={`p-3 rounded cursor-pointer transition ${
                      selectedBook?.id === book.id ? 'bg-blue-50 border-blue-200' : 'hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <h4 className="font-medium text-sm truncate">{book.title}</h4>
                        <div className="flex items-center gap-2 mt-1">
                          <Badge tone="info">{book.structure_type}</Badge>
                          <span className="text-xs text-gray-500">{book.chapter_count} chapters</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-8 text-gray-500 text-sm">
                  No books yet. Generate one to get started.
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* Book Preview */}
        <div className="lg:col-span-2">
          {selectedBook ? (
            <Card>
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h2 className="text-xl font-semibold">{selectedBook.title}</h2>
                  {selectedBook.subtitle && (
                    <p className="text-sm text-gray-600 mt-1">{selectedBook.subtitle}</p>
                  )}
                  <div className="flex items-center gap-2 mt-2">
                    <Badge tone="info">{selectedBook.structure_type}</Badge>
                    <span className="text-sm text-gray-500">
                      {selectedBook.chapter_count} chapters
                    </span>
                    <span className="text-sm text-gray-500">
                      {new Date(selectedBook.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
                <div className="flex gap-2">
                  <select
                    value={exportFormat}
                    onChange={(e) => setExportFormat(e.target.value)}
                    className="px-2 py-1 border rounded text-sm"
                  >
                    <option value="markdown">Markdown</option>
                    <option value="html">HTML</option>
                    <option value="pdf">PDF</option>
                    <option value="epub">EPUB</option>
                  </select>
                  <button
                    onClick={() => handleExportBook(exportFormat)}
                    className="px-3 py-1.5 text-sm bg-green-600 text-white rounded hover:bg-green-700"
                  >
                    Export
                  </button>
                  <button
                    onClick={() => handleDeleteBook(selectedBook.id)}
                    className="px-3 py-1.5 text-sm bg-red-600 text-white rounded hover:bg-red-700"
                  >
                    Delete
                  </button>
                </div>
              </div>

              {selectedBook.description && (
                <p className="text-sm text-gray-600 mb-4">{selectedBook.description}</p>
              )}

              <div className="prose prose-sm max-w-none">
                <div 
                  className="markdown-content"
                  dangerouslySetInnerHTML={{ 
                    __html: selectedBook.content_html || selectedBook.content_markdown
                      .replace(/\n/g, '<br>')
                      .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
                      .replace(/`([^`]+)`/g, '<code>$1</code>')
                      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
                      .replace(/\*([^*]+)\*/g, '<em>$1</em>')
                      .replace(/^## (.+)$/gm, '<h3>$1</h3>')
                      .replace(/^# (.+)$/gm, '<h2>$1</h2>')
                  }}
                />
              </div>

              <div className="mt-6 pt-4 border-t">
                <h4 className="text-sm font-medium mb-2">Source Knowledge Objects</h4>
                <p className="text-sm text-gray-600">
                  Generated from {selectedBook.source_ko_ids.length} knowledge objects
                </p>
              </div>
            </Card>
          ) : (
            <Card>
              <div className="text-center py-12 text-gray-500">
                <div className="text-4xl mb-4">📚</div>
                <p>Select a book to view its content</p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
