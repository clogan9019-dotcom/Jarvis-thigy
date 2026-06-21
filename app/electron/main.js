import { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, shell } from 'electron';
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let win, tray, pyProc;
const isDev = !app.isPackaged;
const BACKEND_PORT = 8765;

function startBackend() {
  if (isDev) return; // run backend manually in dev
  const backendPath = path.join(process.resourcesPath, 'backend');
  const pyExe = path.join(backendPath, 'dist', 'jarvis_backend', 'jarvis_backend.exe');
  const fallbackPy = process.platform === 'win32' ? 'python' : 'python3';
  try {
    pyProc = spawn(pyExe, [], { cwd: backendPath, windowsHide: true });
  } catch {
    pyProc = spawn(fallbackPy, [path.join(backendPath, 'main.py')], { cwd: backendPath, windowsHide: true });
  }
  pyProc?.stdout?.on('data', d => console.log('[py]', d.toString()));
  pyProc?.stderr?.on('data', d => console.error('[py]', d.toString()));
}

function createWindow() {
  win = new BrowserWindow({
    width: 1120,
    height: 720,
    minWidth: 980,
    minHeight: 620,
    backgroundColor: '#060b12',
    frame: false,
    transparent: false,
    titleBarStyle: 'hidden',
    vibrancy: 'dark',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    },
    show: false,
    icon: path.join(__dirname, '../build/icon.png')
  });

  if (isDev) {
    win.loadURL('http://localhost:5173');
    win.webContents.openDevTools({ mode: 'detach' });
  } else {
    win.loadFile(path.join(__dirname, '../dist/index.html'));
  }
  win.once('ready-to-show', () => win.show());
  win.webContents.setWindowOpenHandler(({url}) => { shell.openExternal(url); return {action:'deny'}; });
}

function createTray() {
  const icon = nativeImage.createEmpty();
  tray = new Tray(icon);
  tray.setToolTip('J.A.R.V.I.S');
  const contextMenu = Menu.buildFromTemplate([
    { label: 'Show JARVIS', click: () => win.show() },
    { label: 'Always on top', type: 'checkbox', click: (e) => win.setAlwaysOnTop(e.checked, 'screen-saver') },
    { type: 'separator' },
    { label: 'Quit', click: () => app.quit() }
  ]);
  tray.setContextMenu(contextMenu);
  tray.on('click', () => win.isVisible() ? win.hide() : win.show());
}

app.whenReady().then(() => {
  startBackend();
  createWindow();
  createTray();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
app.on('before-quit', () => { try { pyProc?.kill(); } catch {} });

ipcMain.handle('win:min', () => win.minimize());
ipcMain.handle('win:max', () => win.isMaximized() ? win.unmaximize() : win.maximize());
ipcMain.handle('win:close', () => win.close());
ipcMain.handle('backend:url', () => `http://127.0.0.1:${BACKEND_PORT}`);
