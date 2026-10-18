import { Routes } from '@angular/router';

export const APP_ROUTES: Routes = [
  { path: 'recording', loadComponent: () => import('./pages/recording/recording.page').then(m => m.RecordingPageComponent), title: 'Enregistrement — Glimio' },
  { path: 'library', loadComponent: () => import('./pages/library/library.page').then(m => m.LibraryPageComponent), title: 'Bibliothèque — Glimio' },
  { path: 'search', loadComponent: () => import('./pages/search/search.page').then(m => m.SearchPageComponent), title: 'Recherche intelligente — Glimio' },
  { path: 'settings', loadComponent: () => import('./pages/settings/settings.page').then(m => m.SettingsPageComponent), title: 'Paramètres — Glimio' },
  { path: '', pathMatch: 'full', redirectTo: 'recording' },
  { path: '**', redirectTo: 'recording' },
];
