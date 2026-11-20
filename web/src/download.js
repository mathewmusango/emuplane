// Save an access key the way the AWS console does: one small CSV, shown once.

// The CSV, with every cell quoted and embedded quotes doubled. One unescaped quote
// would turn five columns into six and a stray newline would split the credential
// across two rows, so this is the part worth keeping separate from the download.
export function credentialsCsv({
  account = '',
  accessKeyId = '',
  secretAccessKey = '',
  region = '',
  username = '',
} = {}) {
  const rows = [
    ['Access key ID', 'Secret access key', 'Region', 'Account', 'IAM user'],
    [accessKeyId, secretAccessKey, region, account, username],
  ]
  const csv = rows
    .map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(','))
    .join('\r\n')
  return `${csv}\r\n`
}

export function downloadCredentials({
  account = '',
  accessKeyId = '',
  secretAccessKey = '',
  region = '',
  username = '',
} = {}) {
  if (!accessKeyId || !secretAccessKey) return false
  const blob = new Blob([credentialsCsv({ account, accessKeyId, secretAccessKey, region, username })], {
    type: 'text/csv;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `ministack-credentials-${accessKeyId}.csv`
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Give the browser a moment to start the download before revoking.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  return true
}
