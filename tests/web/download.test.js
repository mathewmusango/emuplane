// The saved CSV is the only copy of an access key a user gets, so its escaping is
// load-bearing. Fuzzed rather than sampled: the inputs that break it (a quote, a comma,
// a CRLF inside a username) are exactly the ones an example test forgets.

import { describe, expect, it } from 'vitest'
import fc from 'fast-check'
import { credentialsCsv, downloadCredentials } from '../../web/src/download'

// RFC 4180 as the export writes it: every cell quoted, quotes doubled, CRLF between rows.
function parseCsv(text) {
  const rows = []
  let row = []
  let cell = ''
  let quoted = false
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i]
    if (quoted) {
      if (char === '"' && text[i + 1] === '"') {
        cell += '"'
        i += 1
      } else if (char === '"') {
        quoted = false
      } else {
        cell += char
      }
    } else if (char === '"') {
      quoted = true
    } else if (char === ',') {
      row.push(cell)
      cell = ''
    } else if (char === '\r' && text[i + 1] === '\n') {
      row.push(cell)
      rows.push(row)
      row = []
      cell = ''
      i += 1
    } else {
      cell += char
    }
  }
  if (cell !== '' || row.length > 0) {
    row.push(cell)
    rows.push(row)
  }
  return rows
}

const cell = fc.string()

describe('the credentials CSV', () => {
  it('round-trips any five credentials through its own escaping', () => {
    fc.assert(
      fc.property(
        cell,
        cell,
        cell,
        cell,
        cell,
        (accessKeyId, secretAccessKey, region, account, username) => {
          const rows = parseCsv(
            credentialsCsv({ accessKeyId, secretAccessKey, region, account, username }),
          )
          expect(rows).toHaveLength(2)
          expect(rows[0]).toHaveLength(5)
          expect(rows[1]).toEqual([accessKeyId, secretAccessKey, region, account, username])
        },
      ),
    )
  })

  it('never lets a cell spill into its neighbour', () => {
    fc.assert(
      fc.property(cell, cell, (accessKeyId, secretAccessKey) => {
        const rows = parseCsv(credentialsCsv({ accessKeyId, secretAccessKey }))
        expect(rows).toHaveLength(2)
        expect(rows[0]).toHaveLength(5)
        expect(rows[1]).toHaveLength(5)
      }),
    )
  })

  it('refuses to write a file without both halves of the key', () => {
    fc.assert(
      fc.property(cell, (accessKeyId) => {
        expect(downloadCredentials({ accessKeyId })).toBe(false)
        expect(downloadCredentials({ secretAccessKey: accessKeyId })).toBe(false)
      }),
    )
  })
})
