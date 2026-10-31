import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  imports: [RouterLink, RouterOutlet],
  template: `
    <header class="top-bar">
      <a class="brand" routerLink="/">Editographer</a>
    </header>
    <main class="page">
      <router-outlet />
    </main>
  `,
  styles: `
    .top-bar {
      display: flex;
      align-items: center;
      height: 56px;
      padding: 0 24px;
      border-bottom: 1px solid var(--border);
    }
    .brand {
      font-weight: 600;
      font-size: 17px;
      color: var(--text);
      text-decoration: none;
    }
    .page {
      max-width: 1080px;
      margin: 0 auto;
      padding: 32px 24px 64px;
    }
    @media (max-width: 600px) {
      .top-bar,
      .page {
        padding-inline: 16px;
      }
      .page {
        padding-top: 20px;
      }
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {}
