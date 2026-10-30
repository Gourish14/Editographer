import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    title: 'Editographer',
    loadComponent: () =>
      import('./features/projects/projects-page').then((page) => page.ProjectsPage),
  },
  {
    path: 'projects/:id',
    title: 'Project',
    loadComponent: () => import('./features/project/project-page').then((page) => page.ProjectPage),
  },
  {
    path: 'projects/:id/render',
    title: 'Render settings',
    loadComponent: () =>
      import('./features/render/render-settings').then((page) => page.RenderSettingsPage),
  },
  {
    path: 'renders/:id',
    title: 'Render',
    loadComponent: () => import('./features/render/render-page').then((page) => page.RenderPage),
  },
  { path: '**', redirectTo: '' },
];
