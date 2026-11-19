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
      items: ['deployment/docker-podman'],
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
      items: ['guides/s3'],
    },
  ],

  // What the console can do, operation by operation, and what it cannot.
  reference: [
    {
      type: 'category',
      label: 'Coverage',
      collapsed: false,
      items: [
        'reference/s3-coverage',
        'reference/s3-files-coverage',
        'reference/iam-coverage',
        'reference/account-coverage',
      ],
    },
    'reference/configuration',
    'reference/limits',
  ],

  // The control API is generated from the control's own route table, so it is its own tab.
  api: ['reference/control-api'],
}
