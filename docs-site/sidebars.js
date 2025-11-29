
module.exports = {
  tutorialSidebar: [
    {
      type: 'category',
      label: 'Overview',
      items: ['overview/intro', 'overview/architecture'],
    },
    {
      type: 'category',
      label: 'Backend',
      items: [
        'backend/architecture',
        'backend/workers',
        'backend/websockets',
        'backend/api-reference'
      ],
    },
    {
      type: 'category',
      label: 'Frontend',
      items: ['frontend/architecture', 'frontend/hooks', 'frontend/pages'],
    },
    {
      type: 'category',
      label: 'Operations',
      items: ['ops/deploy', 'ops/run-local'],
    },
  ],
};
