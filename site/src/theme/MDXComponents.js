import React from 'react'
import MDXComponents from '@theme-original/MDXComponents'

// External links open in their own tab; internal ones stay in place.
function ExternalAnchor({ href, ...props }) {
  const external = /^https?:\/\//i.test(href || '')
  return (
    <a
      {...props}
      href={href}
      {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
    />
  )
}

export default {
  ...MDXComponents,
  a: ExternalAnchor,
}
