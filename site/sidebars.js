// One sidebar per navbar tab. A doc belongs to exactly one of them, so no page is
// reachable twice and each tab's sidebar is the whole of that area.
module.exports = {
  // The tutorial: read this first, then the pages behind each idea.
  docs: [
    'intro',
    {
      type: 'category',
      label: 'Getting started',
      collapsed: false,
      items: [
        'getting-started/quickstart',
        'getting-started/access',
        'getting-started/console',
        'getting-started/access-keys',
      ],
    },
    {
      type: 'category',
      label: 'Deployment',
      collapsed: false,
      items: [
        'deployment/docker-podman',
        'deployment/docker',
        'deployment/podman',
        'deployment/upgrading',
      ],
    },
    {
      type: 'category',
      label: 'Concepts',
      collapsed: false,
      items: ['concepts/architecture', 'concepts/tenancy', 'concepts/extensions'],
    },
    {
      type: 'category',
      label: 'Guides',
      collapsed: false,
      items: ['guides/s3', 'guides/troubleshooting'],
    },
    {
      // The operator side: how the thing is run, released and versioned.
      type: 'category',
      label: 'Operations',
      collapsed: false,
      items: [
        'operations/runbook',
        'operations/releases',
        'operations/image-and-versions',
      ],
    },
  ],

  // What the console can do, operation by operation, and what it cannot.
  // One page per service sits behind the generated reference index; the sidebar
  // does not grow a line per service, because that list is the index's table.
  reference: [
    'reference/index',
    'reference/configuration',
    'reference/limits',
  ],

  // The control API is generated from the control's own route table, so it is its own tab.
  api: ['reference/control-api'],
}
